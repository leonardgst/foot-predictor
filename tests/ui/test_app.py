"""Écrans de l'interface (`streamlit.testing.v1.AppTest`) sur un faux transport `httpx` : aucun serveur.

`AppTest` exécute le script dans le processus des tests ; le client de l'interface prend alors le
faux transport `ui.client.TRANSPORT`, comme il prendrait le réseau local en vrai.
"""

from __future__ import annotations

import ast
import datetime as dt
from pathlib import Path

import pytest
from streamlit.testing.v1 import AppTest

from foot_predictor.ui import client as client_module
from tests.ui.fake_api import DAY, FakeApi

APP = Path(__file__).resolve().parents[2] / "src" / "foot_predictor" / "ui" / "app.py"
UI_DIR = APP.parent


@pytest.fixture
def api(monkeypatch):
    fake = FakeApi()
    monkeypatch.setattr(client_module, "TRANSPORT", fake.transport())
    return fake


def start(day: str | None = DAY) -> AppTest:
    at = AppTest.from_file(str(APP), default_timeout=30).run()
    assert not at.exception, at.exception
    if day:
        at.date_input(key="date_replay").set_value(dt.date.fromisoformat(day)).run()
    return at


def texts(at: AppTest) -> str:
    parts = [m.value for m in at.markdown] + [c.value for c in at.caption]
    parts += [e.value for e in at.error] + [i.value for i in at.info]
    return "\n".join(parts)


def test_matches_screen_lists_matches_with_badges_and_buttons(api):
    at = start()
    assert not at.exception
    page = texts(at)
    assert "🟢 disponible" in page and "🔴 indisponible" in page and "⚪ hors périmètre" in page
    assert at.button(key="predict_1").disabled is False
    assert at.button(key="predict_2").disabled is True and at.button(key="predict_3").disabled is True
    assert "730 jours" in (at.button(key="predict_2").help or "")
    assert ("GET", "/matches", {"date": DAY, "mode": "replay"}) in api.calls


def test_prediction_button_opens_the_detail_screen(api):
    at = start()
    at.button(key="predict_1").click().run()
    assert not at.exception and at.session_state.screen == "Détail"
    h1, h2 = at.metric[:4], at.metric[4:]  # H1 à gauche, H2 à droite
    metrics = {m.label: m.value for m in h1}
    assert metrics["E[T] (buts attendus)"] == "2,73" and metrics["P(T > 2,5)"] == "55,0 %"
    assert metrics["λ domicile"] == "1,62" and metrics["λ extérieur"] == "1,11"
    assert [m.value for m in h2] == ["2,75", "57,0 %", "1,70", "1,05"]
    page = texts(at)
    assert "[1 ; 4] buts, couverture annoncée 77,0 %" in page
    assert "Score réel (rejeu) : 2 – 1 (total 3)" in page
    assert "Référence de marché" in page and "52,0 %" in page
    assert "rejeu-2023-essai" in page and "créée maintenant" in page
    assert any(call[0] == "POST" for call in api.calls)
    posts = [call[2] for call in api.calls if call[0] == "POST"]
    assert {p.get("horizon", "H1") for p in posts} == {"H1", "H2"}  # les deux horizons, côte à côte


def test_variables_button_shows_the_missing_variable_without_prediction(api):
    at = start()
    at.button(key="variables_2").click().run()
    assert not at.exception and at.session_state.screen == "Détail"
    assert not at.metric  # aucune prédiction pour un match indisponible
    page = texts(at)
    assert "1 présentes, 1 manquantes ou périmées" in page and "730 jours" in page
    assert all(call[0] == "GET" for call in api.calls)
    assert any(call[2].get("horizon") == "H2" for call in api.calls)  # H2 demandé aussi, indisponible de même


def test_sealed_date_in_live_mode_is_a_readable_error(api, monkeypatch):
    at = start(day=None)
    at.radio(key="mode_label").set_value("Live").run()
    at.date_input(key="date_live").set_value(dt.date.fromisoformat("2025-08-16")).run()
    assert not at.exception
    assert at.error and "Date refusée (saison scellée" in at.error[0].value and "scellés" in at.error[0].value


def test_unreachable_api_is_reported_with_the_command_to_start_it(monkeypatch):
    import httpx

    def refuse(request):
        raise httpx.ConnectError("refusée", request=request)

    monkeypatch.setattr(client_module, "TRANSPORT", httpx.MockTransport(refuse))
    at = AppTest.from_file(str(APP), default_timeout=30).run()
    assert not at.exception
    assert "API injoignable" in at.error[0].value and "foot_predictor.api serve" in at.error[0].value


def test_detail_screen_without_a_chosen_match_says_what_to_do(api):
    at = start(day=None)
    at.sidebar.radio(key="screen").set_value("Détail").run()
    assert not at.exception and "Choisir un match" in at.info[0].value


def test_model_screen_shows_card_validation_and_freshness(api):
    at = start(day=None)
    at.sidebar.radio(key="screen").set_value("Modèle").run()
    assert not at.exception
    page = texts(at)
    assert "`is_home`" in page and "Horizon H1 : aucune information de composition." in page
    assert "API : ok" in page
    assert len(at.dataframe) >= 3  # validation, comparaisons, fraîcheur
    assert at.get("image")  # courbe d'apport (figure versionnée de docs/resultats/figures/)
    assert {("GET", "/models/active"), ("GET", "/data/freshness"), ("GET", "/health")} <= {c[:2] for c in api.calls}


def test_the_interface_imports_neither_the_database_nor_the_business_logic():
    """ADR-0040 : l'interface ne parle qu'à l'API ; seuls `foot_predictor.ui.*` et des paquets tiers d'affichage."""
    allowed_third_party = {"streamlit", "httpx", "pandas"}
    for path in UI_DIR.glob("*.py"):
        tree = ast.parse(path.read_text(encoding="utf-8"))
        for node in ast.walk(tree):
            names = []
            if isinstance(node, ast.Import):
                names = [alias.name for alias in node.names]
            elif isinstance(node, ast.ImportFrom) and node.module:
                names = [node.module]
            for name in names:
                root = name.split(".")[0]
                if root == "foot_predictor":
                    assert name.startswith("foot_predictor.ui"), f"{path.name} importe {name}"
                else:
                    assert root in allowed_third_party or root in {"__future__", "datetime", "os", "pathlib",
                                                                   "dataclasses"}, f"{path.name} importe {name}"  # fmt: skip


def titles(at: AppTest) -> list[str]:
    return [s.value for s in at.subheader]


def test_detail_shows_h1_and_h2_side_by_side_with_what_the_composition_changes(api):
    at = start()
    at.button(key="predict_1").click().run()
    assert not at.exception
    assert "H1 · sans composition" in titles(at) and "H2 · avec composition" in titles(at)
    assert "Ce que la composition change" in titles(at)
    difference = next(df.value for df in at.dataframe if "Écart H2 − H1" in df.value.columns)
    assert list(difference["Grandeur"]) == ["E[T] (buts attendus)", "λ domicile", "λ extérieur", "P(T > 2,5)"]
    assert list(difference["Écart H2 − H1"]) == ["+0,02", "+0,08", "-0,06", "+2,0 points"]
    composition = next(
        df.value for df in at.dataframe if list(df.value.columns) == ["Variable", "Domicile", "Extérieur"]
    )
    quality = composition[composition["Variable"].str.startswith("Qualité")].iloc[0]
    assert quality["Domicile"] == "7,125" and quality["Extérieur"] == "6,980"
    regulars = composition[composition["Variable"].str.startswith("Part")].iloc[0]
    assert regulars["Extérieur"] == "manquante"  # jamais une valeur de remplacement
    assert "moins de 0,1 %" in texts(at)


def test_live_h2_shows_its_reason_and_no_prediction(api):
    at = start(day=None)
    at.radio(key="mode_label").set_value("Live").run()
    at.date_input(key="date_live").set_value(dt.date.fromisoformat(DAY)).run()
    at.button(key="predict_1").click().run()
    assert not at.exception and at.session_state.screen == "Détail"
    page = texts(at)
    assert "non disponible en live (ADR-0010)" in page
    assert len(at.metric) == 4  # H1 seulement
    assert "Ce que la composition change" not in titles(at)


def test_an_error_common_to_both_horizons_is_shown_once(api):
    at = start(day=None)
    at.radio(key="mode_label").set_value("Live").run()
    at.date_input(key="date_live").set_value(dt.date.fromisoformat("2025-08-16")).run()
    assert len(at.error) == 1  # l'erreur de date n'est pas dupliquée pour H2


def test_contribution_screen_shows_the_decision_path_and_the_cautions(api):
    at = start(day=None)
    at.sidebar.radio(key="screen").set_value("Apport des variables").run()
    assert not at.exception
    page = texts(at)
    assert "ds-essai-h2" in page and "Le gain de G5 est minuscule." in page
    steps = next(df.value for df in at.dataframe if "Verdict" in df.value.columns)
    assert list(steps["Verdict"]) == ["non retenu", "retenu", "non retenu"]
    assert steps["Gain de log-loss [IC 95 %]"].iloc[1] == "+0,00078 [+0,00003 ; +0,00151]"
    assert ("GET", "/models/h2/contribution", {}) in api.calls
