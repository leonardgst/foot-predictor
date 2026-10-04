"""Mise en forme de l'interface : pastilles, loi du total dans l'ordre, intervalle et couverture, variables."""

from __future__ import annotations

from foot_predictor.ui import views
from tests.ui.fake_api import CARD, MATCHES, PREDICTION, VARIABLES_MISSING


def test_only_available_matches_can_be_predicted():
    assert [views.can_predict(m) for m in MATCHES] == [True, False, False]
    assert views.badge("unavailable").startswith("🔴") and views.badge("inconnu").startswith("?")
    assert set(views.STATUS_LEGEND) == set(views.STATUS_BADGES)


def test_matches_table_shows_badges_and_reasons():
    frame = views.matches_frame(MATCHES)
    assert list(frame["Disponibilité"]) == ["🟢 disponible", "🔴 indisponible", "⚪ hors périmètre"]
    assert "730 jours" in frame.loc[1, "Raisons"] and frame.loc[0, "Heure"] == "15:00 UTC"
    assert views.matches_frame([]).empty
    assert views.status_counts(MATCHES) == {"available": 1, "unavailable": 1, "out_of_scope": 1}


def test_distribution_keeps_the_order_0_to_10_plus_and_marks_the_interval():
    frame = views.distribution_frame(PREDICTION)
    assert list(frame["Buts"]) == [*map(str, range(10)), "10+"]
    assert abs(frame["Probabilité"].sum() - 1) < 1e-9
    inside = frame.loc[frame["Intervalle"] == "dans [q10 ; q90]", "Buts"].tolist()
    assert inside == ["1", "2", "3", "4"]


def test_interval_is_always_given_with_its_announced_coverage():
    assert views.interval_text(PREDICTION) == "[1 ; 4] buts, couverture annoncée 77,0 %"
    ten_plus = PREDICTION | {"interval": {"low": 2, "high": 10, "high_label": "10+", "announced_coverage": 0.805}}
    assert views.interval_text(ten_plus) == "[2 ; 10+] buts, couverture annoncée 80,5 %"
    assert views.percent(None) == "n. d." and views.number(1.234) == "1,23"


def test_variables_table_keeps_missing_values_empty_with_their_reason():
    frame = views.variables_frame(VARIABLES_MISSING)
    missing = frame[frame["Statut"] == "🔴 manquante"].iloc[0]
    assert missing["Valeur"] == "" and "730 jours" in missing["Raison"]  # aucune valeur de remplacement
    assert frame.iloc[0]["Valeur"] == "1500,000" and frame.iloc[0]["Côté"] == "domicile"


def test_actual_score_and_the_probability_the_model_gave():
    answer = {"actual_score": {"home": 2, "away": 1}, "prediction": PREDICTION}
    assert views.actual_score_text(answer) == "2 – 1 (total 3) ; le modèle donnait P(T = 3) = 22,0 %"
    big = {"actual_score": {"home": 7, "away": 4}, "prediction": PREDICTION}
    assert "P(T = 10+)" in views.actual_score_text(big)
    assert views.actual_score_text({"actual_score": None}) is None
    assert views.actual_score_text({"actual_score": {"home": None, "away": None}}) is None


def test_problem_titles_name_the_cause():
    assert "scellée" in views.problem_title(403) and "indisponible" in views.problem_title(409)
    assert views.problem_title(None) == "API injoignable" and "418" in views.problem_title(418)


def test_model_card_tables():
    summary = dict(views.card_summary(CARD))
    assert summary["Version"] == "scelle-h1-essai" and summary["Contient des matchs scellés"] == "non"
    assert "half_life = 240" in summary["Hyperparamètres retenus"]
    validation = views.validation_frame(CARD)
    assert validation.loc[validation["Métrique"] == "Log-loss du total", "Valeur"].item() == "1,8805"
    comparison = views.comparisons_frame(CARD).iloc[0]
    assert comparison["IC 95 %"] == "[0,0133 ; 0,0226]" and comparison["Significatif"].startswith("oui")
    assert views.validation_frame({}).empty and views.comparisons_frame({}).empty
    assert views.limits_list(CARD) == ["Horizon H1 : aucune information de composition."]


def test_competition_label_flags_what_the_model_does_not_cover():
    assert views.competition_label({"id": 1, "name": "Ligue A", "country": "Pays", "in_model_scope": True}) == (
        "Ligue A (Pays)"
    )
    assert views.competition_label({"id": 2, "name": None, "in_model_scope": False}) == (
        "championnat 2 · hors périmètre"
    )
