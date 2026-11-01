"""Inférence à l'horizon H2 (6.10, ADR-0050) : même fonction que l'entraînement, composition du match sans ses
résultats, rejeu seulement, jamais de valeur de remplacement. Données synthétiques, aucune base."""

from __future__ import annotations

import datetime as dt

import numpy as np
import pandas as pd
import pytest

from foot_predictor.features.dataset import build_frame_h2
from foot_predictor.inference import models
from foot_predictor.inference import predict as P
from foot_predictor.inference.availability import (
    AVAILABLE,
    EXCLUDED,
    H2_LIVE_REASON,
    H2_UNAVAILABLE,
    OUT_OF_SCOPE,
    UNAVAILABLE,
    missing_reason,
)
from foot_predictor.inference.models import LoadedModel
from foot_predictor.inference.rows import (
    POST_MATCH_COLUMNS,
    POST_MATCH_LINEUP_COLUMNS,
    RowsCache,
    history_for_day,
    lineups_for_day,
    rows_for_day,
)
from foot_predictor.modeling.models.base import MatchPredictions, match_frame
from foot_predictor.modeling.models.team import M3
from foot_predictor.seal import H1_SEALED_EXPERIMENT, SEALED_DONE
from tests.features.test_dataset import COEF, PARAMS
from tests.features.test_dataset_h2 import synthetic_compositions
from tests.inference.test_predict import FakeModel, context, shifted_matches

KW = {"elo_params": PARAMS, "coefficients": COEF, "periods": None}
H2_GROUPS = ("G0", "G1", "G2", "G5")


class FakeModelH2(FakeModel):
    """Mêmes variables requises que le modèle H2 retenu (G0 + G1 + G2 + G5), λ fixes."""

    def __init__(self):
        self.features = M3(H2_GROUPS, 60).features

    def predict(self, rows):
        matches = match_frame(rows)
        n = len(matches)
        return MatchPredictions.independent_poisson(matches.index.to_numpy(), np.full(n, 1.5), np.full(n, 1.0))


@pytest.fixture(scope="module")
def setup():
    matches = shifted_matches()
    lineups, sheets = synthetic_compositions(matches)
    full = build_frame_h2(matches, lineups, sheets, PARAMS, COEF)
    return matches, lineups, sheets, full


def league_days(matches, season=None):
    league = matches[(matches["api_league_id"] == 39) & (matches["status"] == "played")]
    if season is not None:
        league = league[league["season_year"] == season]
    return sorted(league["match_day"].unique())


def h2_rows(matches, lineups, sheets, day, **kwargs):
    return rows_for_day(matches, day, horizon="H2", lineups=lineups, team_sheets=sheets, **KW, **kwargs)


def h2_context(matches, lineups, sheets, **kwargs):
    """Contexte d'inférence avec un modèle H1 et un modèle H2 factices et la lecture des compositions injectée."""
    ctx = context(matches, LoadedModel("essai", FakeModel(), {"version": "essai"}, None), **kwargs)
    h2 = LoadedModel("essai-h2", FakeModelH2(), {"version": "essai-h2", "horizon": "H2"}, None)
    for season in (2022, 2023):
        ctx._models[("replay", season, "H2")] = h2
    ctx.h2_loader = lambda: (lineups, sheets)
    return ctx


# ------------------------------------------------------------------------------------------ les lignes


def test_h2_rows_equal_the_training_rows_bit_for_bit_on_several_days(setup):
    """Contrôle (a) de l'ADR-0040 à l'horizon H2 : lignes d'inférence = lignes du jeu H2, hors colonnes d'après-match."""
    matches, lineups, sheets, full = setup
    expected_all = full.drop(columns=list(POST_MATCH_COLUMNS))
    days = league_days(matches)
    assert len(days) >= 12
    for day in days:
        rows = h2_rows(matches, lineups, sheets, day).reset_index(drop=True)
        expected = expected_all[expected_all["match_day"] == day].reset_index(drop=True)
        pd.testing.assert_frame_equal(rows, expected, check_exact=True)


def test_h2_rows_carry_the_h2_columns_and_h1_rows_do_not(setup):
    matches, lineups, sheets, _ = setup
    day = league_days(matches, 2022)[-1]
    h1 = rows_for_day(matches, day, **KW)
    h2 = h2_rows(matches, lineups, sheets, day)
    assert "xi_quality" in h2.columns and "xi_quality" not in h1.columns
    pd.testing.assert_frame_equal(h2[list(h1.columns)].reset_index(drop=True), h1.reset_index(drop=True))


def test_what_the_target_match_produces_changes_nothing(setup):
    """Minutes, note, remplaçant et capitaine du match cible sont retirés : les modifier ne change aucune ligne."""
    matches, lineups, sheets, _ = setup
    day = league_days(matches, 2022)[-1]
    base = h2_rows(matches, lineups, sheets, day)
    targets = matches.loc[matches["match_day"] == day, "match_id"]
    changed = lineups.copy()
    on_target = changed["match_id"].isin(targets)
    changed.loc[on_target, "minutes"] = 1
    changed.loc[on_target, "rating"] = 3.1
    pd.testing.assert_frame_equal(h2_rows(matches, changed, sheets, day), base, check_exact=True)


def test_later_compositions_change_nothing(setup):
    matches, lineups, sheets, _ = setup
    day = league_days(matches, 2022)[len(league_days(matches, 2022)) // 2]
    base = h2_rows(matches, lineups, sheets, day)
    later = matches.loc[matches["match_day"] > day, "match_id"]
    changed = lineups.copy()
    after = changed["match_id"].isin(later)
    changed.loc[after, "api_player_id"] += 9000
    changed.loc[after, "rating"] = 4.0
    pd.testing.assert_frame_equal(h2_rows(matches, changed, sheets, day), base, check_exact=True)


def test_lineups_for_day_keeps_what_is_known_at_t_minus_60_and_blanks_the_rest(setup):
    matches, lineups, sheets, _ = setup
    day = league_days(matches, 2022)[5]
    targets = matches.loc[(matches["match_day"] == day) & (matches["api_league_id"] == 39), "match_id"]
    history = history_for_day(matches, day, targets)
    kept, kept_sheets = lineups_for_day(lineups, sheets, history, targets)
    assert kept["match_id"].isin(history["match_id"]).all() and kept_sheets["match_id"].isin(history["match_id"]).all()
    on_target = kept["match_id"].isin(targets)
    assert on_target.any() and kept.loc[on_target, "started"].all()  # les titulaires restent
    for column in POST_MATCH_LINEUP_COLUMNS:
        if column in kept.columns:
            assert kept.loc[on_target, column].isna().all(), column
    earlier = ~on_target
    assert kept.loc[earlier, "rating"].notna().any() and kept.loc[earlier, "minutes"].notna().all()
    assert lineups["rating"].notna().all()  # la table d'origine n'est pas modifiée


def test_h2_needs_compositions_and_a_known_horizon(setup):
    matches, _, _, _ = setup
    day = league_days(matches, 2022)[-1]
    with pytest.raises(ValueError, match="compositions"):
        rows_for_day(matches, day, horizon="H2", **KW)
    with pytest.raises(ValueError, match="Horizon inconnu"):
        rows_for_day(matches, day, horizon="H3", **KW)


def test_the_rows_cache_keeps_horizons_apart(setup, monkeypatch):
    matches, lineups, sheets, _ = setup
    day = league_days(matches, 2022)[5]
    calls = []
    import foot_predictor.inference.rows as module

    real = module.rows_for_day
    monkeypatch.setattr(module, "rows_for_day", lambda m, d, **k: calls.append(k["horizon"]) or real(m, d, **KW | k))
    cache = RowsCache(matches, "v1", lineups=lineups, team_sheets=sheets)
    h1, h2 = cache.rows(day), cache.rows(day, "H2")
    assert cache.rows(day, "H2") is h2 and cache.rows(day) is h1
    assert calls == ["H1", "H2"] and "xi_quality" in h2.columns and "xi_quality" not in h1.columns


def test_the_compositions_are_read_at_the_first_h2_request_only(setup):
    matches, lineups, sheets, _ = setup
    reads = []
    ctx = context(matches, LoadedModel("essai", FakeModel(), {"version": "essai"}, None))
    ctx.h2_loader = lambda: reads.append(1) or (lineups, sheets)
    day = league_days(matches, 2023)[3]
    ctx.rows(day)  # H1 : aucune lecture des compositions
    assert reads == []
    ctx.rows(day, "H2"), ctx.rows(league_days(matches, 2023)[4], "H2")
    assert reads == [1]
    empty = context(matches, LoadedModel("essai", FakeModel(), {"version": "essai"}, None))
    empty.h2_loader = lambda: (lineups.iloc[0:0], sheets.iloc[0:0])  # base sans composition
    with pytest.raises(P.H2SourcesMissing, match="aucune composition"):
        empty.rows(day, "H2")
    bare = context(matches, LoadedModel("essai", FakeModel(), {"version": "essai"}, None))
    with pytest.raises(P.H2SourcesMissing, match="H2"):
        bare.rows(day, "H2")


# ----------------------------------------------------------------------------------- les prédictions


def an_h2_target(matches, season, late=True):
    league = matches[(matches["api_league_id"] == 39) & (matches["season_year"] == season)]
    league = league[league["status"] == "played"].sort_values(["match_day", "match_id"])
    return league.iloc[-1] if late else league.iloc[0]


def test_a_late_replay_match_gets_an_h2_prediction_with_the_composition_variables(setup):
    matches, lineups, sheets, _ = setup
    ctx = h2_context(matches, lineups, sheets)
    target = an_h2_target(matches, 2023)
    (answer,) = [
        a
        for a in P.predict_day(target["match_day"], "replay", ctx, horizon="H2")
        if a["match_id"] == target["match_id"]
    ]
    assert answer["horizon"] == "H2" and answer["status"] == AVAILABLE and answer["model_version"] == "essai-h2"
    assert answer["prediction"]["lambda_home"] == 1.5 and answer["actual_score"] is not None
    names = {v["variable"] for v in answer["availability"]}
    assert {"xi_quality", "opp_xi_quality", "xi_regulars_missing", "xi_mean_age"} <= names
    assert {v["status"] for v in answer["availability"]} == {"presente"}
    (h1,) = [
        a
        for a in P.predict_day(target["match_day"], "replay", ctx, horizon="H1")
        if a["match_id"] == target["match_id"]
    ]
    assert (
        h1["horizon"] == "H1"
        and h1["model_version"] == "essai"
        and "xi_quality" not in {v["variable"] for v in h1["availability"]}
    )  # H1 inchangé : aucune variable de composition


def test_an_early_match_is_unavailable_with_the_composition_reasons_and_no_replacement(setup):
    matches, lineups, sheets, _ = setup
    ctx = h2_context(matches, lineups, sheets)
    first = matches.loc[matches["api_league_id"] == 39, "match_day"].min()
    answers = [a for a in P.predict_day(first, "replay", ctx, horizon="H2") if a["api_league_id"] == 39]
    assert answers and all(a["status"] == UNAVAILABLE and a["prediction"] is None for a in answers)
    reasons = " ".join(answers[0]["reasons"])
    assert "qualité du onze" in reasons or "habituels absents" in reasons


def test_a_match_without_composition_is_unavailable_not_filled(setup):
    matches, lineups, sheets, _ = setup
    target = an_h2_target(matches, 2023)
    stripped = lineups[lineups["match_id"] != target["match_id"]]  # aucune composition pour ce match
    ctx = h2_context(matches, stripped, sheets)
    (answer,) = [
        a
        for a in P.predict_day(target["match_day"], "replay", ctx, horizon="H2")
        if a["match_id"] == target["match_id"]
    ]
    assert answer["status"] == UNAVAILABLE and answer["prediction"] is None
    assert any("xi_quality" in r and "onze incomplet" in r for r in answer["reasons"])


def test_the_composition_reasons_are_written_for_each_h2_variable():
    assert "onze incomplet" in missing_reason("xi_quality") and "de l'adversaire" in missing_reason("opp_xi_quality")
    assert "10 matchs" in missing_reason("xi_regulars_missing")
    assert "naissance" in missing_reason("opp_xi_mean_age")


def test_live_h2_is_unavailable_with_its_reason_and_reads_nothing(tmp_path):
    """ADR-0010 : aucune composition après la fin de l'abonnement ; ni modèle, ni compositions, ni variable."""
    matches = shifted_matches(years=6)
    log = tmp_path / "journal.md"
    log.write_text(f"| x | y | {H1_SEALED_EXPERIMENT} | {SEALED_DONE}, rapport z |\n", encoding="utf-8")
    upcoming = matches[matches["status"] != "played"].iloc[0]
    ctx = context(
        matches,
        LoadedModel("essai", FakeModel(), {"version": "essai"}, None),
        sealed_log=log,
        today=upcoming["match_day"],
        history_opened=True,
    )

    def refuse():
        raise AssertionError("le live H2 ne lit aucune composition")

    ctx.h2_loader = refuse
    answers = P.predict_day(upcoming["match_day"], "live", ctx, match_ids=[upcoming["match_id"]], horizon="H2")
    (answer,) = answers
    assert answer["status"] == H2_UNAVAILABLE and answer["reasons"] == [H2_LIVE_REASON]
    assert answer["model_version"] is None and answer["availability"] == [] and answer["prediction"] is None
    assert answer["horizon"] == "H2" and answer["mode"] == "live" and answer["market_reference"] is None
    assert "ADR-0010" in H2_LIVE_REASON
    cup = matches[matches["competition_kind"] == "cup"].iloc[0]
    d2 = matches[matches["api_league_id"] == 40].iloc[0]
    for other in (cup, d2):  # hors périmètre : le statut de H1, pas « H2 non disponible »
        live = P.h2_live_answer(other, ctx)
        assert live["status"] == OUT_OF_SCOPE and live["reasons"] != [H2_LIVE_REASON] and live["horizon"] == "H2"
    excluded = upcoming.copy()
    excluded["excluded"] = True
    assert P.h2_live_answer(excluded, ctx)["status"] == EXCLUDED
    with pytest.raises(models.ModelUnavailable, match="live"):
        ctx.model(upcoming["match_day"], "live", "H2")


def test_h2_replay_is_closed_on_the_sealed_seasons_like_h1(setup, tmp_path):
    matches, lineups, sheets, _ = setup
    ctx = h2_context(matches, lineups, sheets, sealed_log=tmp_path / "journal.md")
    for day in (dt.date(2025, 8, 16), dt.date(2020, 10, 3)):
        with pytest.raises(P.ReferenceDateRefused):
            P.predict_day(day, "replay", ctx, horizon="H2")
    with pytest.raises(ValueError, match="Horizon inconnu"):
        P.predict_day(dt.date(2023, 1, 1), "replay", ctx, horizon="H3")
