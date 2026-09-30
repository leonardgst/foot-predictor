"""Disponibilité et prédiction : statuts, raisons, intervalle et couverture, refus du scellé. Données synthétiques."""

from __future__ import annotations

import datetime as dt

import numpy as np
import pandas as pd
import pytest
from scipy.stats import poisson

from foot_predictor.features.dataset import build_frame
from foot_predictor.inference import predict as P
from foot_predictor.inference.availability import (
    AVAILABLE,
    EXCLUDED,
    H2_UNAVAILABLE,
    OUT_OF_SCOPE,
    STALE,
    UNAVAILABLE,
    Freshness,
    match_availability,
)
from foot_predictor.inference.models import LoadedModel
from foot_predictor.inference.rows import rows_for_day
from foot_predictor.modeling.models.base import MatchPredictions, match_frame
from foot_predictor.modeling.models.team import M3
from tests.features.test_dataset import COEF, PARAMS, synthetic_matches

KW = {"elo_params": PARAMS, "coefficients": COEF, "periods": None}
YEARS = 3  # 2019-2020 décalés en 2022-2023 : saisons de rejeu ouvertes


def shifted_matches() -> pd.DataFrame:
    matches = synthetic_matches()
    matches["match_date"] = matches["match_date"] + pd.DateOffset(years=YEARS)
    matches["match_day"] = matches["match_date"].dt.date
    matches["season_year"] = matches["season_year"] + YEARS
    matches["origin"] = "api"
    return matches


class FakeModel:
    """Même interface que M3, mêmes variables requises (G0 + G1 + G2, demi-vie 60), λ fixes : la logique testée
    ici est la disponibilité et la réponse, pas l'ajustement (le jeu synthétique est trop petit pour 18 coefficients)."""

    name = "faux"

    def __init__(self):
        self.features = M3(("G0", "G1", "G2"), 60).features

    def predict(self, rows):
        matches = match_frame(rows)
        n = len(matches)
        return MatchPredictions.independent_poisson(matches.index.to_numpy(), np.full(n, 1.4), np.full(n, 1.1))


@pytest.fixture(scope="module")
def setup():
    matches = shifted_matches()
    dataset = build_frame(matches, PARAMS, COEF)
    loaded = LoadedModel("essai", FakeModel(), {"version": "essai"}, None)
    return matches, dataset, loaded


def context(matches, loaded, **kwargs):
    ctx = P.InferenceContext(
        matches=matches, data_version="v-test",
        freshness=Freshness("staging", matches["match_day"].max()),
        team_names={1: "Club Un"}, **kwargs,
    )  # fmt: skip
    ctx._models[("replay", 2022)] = loaded
    ctx._models[("replay", 2023)] = loaded
    ctx._models[("live", "actif")] = loaded
    return ctx


def day_of(matches, predicate):
    return matches[predicate(matches)].iloc[0]


def test_distribution_summary_matches_a_known_poisson():
    total = np.append(poisson.pmf(np.arange(10), 2.8), poisson.sf(9, 2.8))
    summary = P.distribution_summary(total)
    assert summary["interval"]["low"] == 1 and summary["interval"]["high"] == 5
    assert summary["interval"]["announced_coverage"] == pytest.approx(poisson.cdf(5, 2.8) - poisson.cdf(0, 2.8))
    assert summary["p_over_2_5"] == pytest.approx(poisson.sf(2, 2.8))
    assert sum(summary["total_distribution"].values()) == pytest.approx(1.0)


def test_available_match_gets_a_full_prediction_and_its_real_score(setup):
    matches, _, loaded = setup
    target = day_of(
        matches, lambda m: (m["api_league_id"] == 39) & (m["season_year"] == 2023) & (m["status"] == "played")
    )
    ctx = context(matches, loaded)
    (answer,) = [a for a in P.predict_day(target["match_day"], "replay", ctx) if a["match_id"] == target["match_id"]]
    assert answer["status"] == AVAILABLE and answer["reasons"] == []
    p = answer["prediction"]
    assert p["expected_total"] == pytest.approx(p["lambda_home"] + p["lambda_away"])
    assert sum(p["total_distribution"].values()) == pytest.approx(1.0)
    assert 0 < p["interval"]["announced_coverage"] < 1
    assert answer["actual_score"] == {"home": int(target["home_goals_90"]), "away": int(target["away_goals_90"])}
    assert {v["status"] for v in answer["availability"]} == {"presente"}


def test_match_without_history_is_unavailable_with_reasons_and_no_prediction(setup):
    matches, _, loaded = setup
    first = matches.loc[matches["api_league_id"] == 39, "match_day"].min()
    answers = [a for a in P.predict_day(first, "replay", context(matches, loaded)) if a["api_league_id"] == 39]
    assert answers and all(a["status"] == UNAVAILABLE and a["prediction"] is None for a in answers)
    assert any("730 jours" in reason for reason in answers[0]["reasons"])


def test_second_division_and_cups_are_out_of_scope(setup):
    matches, _, loaded = setup
    d2 = day_of(matches, lambda m: m["api_league_id"] == 40)
    answers = P.predict_day(d2["match_day"], "replay", context(matches, loaded), match_ids=[d2["match_id"]])
    assert answers[0]["status"] == OUT_OF_SCOPE and answers[0]["prediction"] is None
    cup = day_of(matches, lambda m: m["competition_kind"] == "cup")
    answers = P.predict_day(cup["match_day"], "replay", context(matches, loaded), match_ids=[cup["match_id"]])
    assert answers[0]["status"] == OUT_OF_SCOPE and "coupe" in answers[0]["reasons"][0]


def test_stale_source_makes_history_variables_stale(setup):
    matches, _, loaded = setup
    target = day_of(
        matches, lambda m: (m["api_league_id"] == 39) & (m["season_year"] == 2023) & (m["status"] == "played")
    )
    rows = rows_for_day(matches, target["match_day"], [target["match_id"]], **KW)
    fresh = Freshness("football_data", target["match_day"] - dt.timedelta(days=10))
    availability = match_availability(target, rows, loaded.model.features, fresh)
    assert availability.status == UNAVAILABLE
    stale = [v for v in availability.variables if v.status == STALE]
    assert stale and all(
        v.variable.startswith(("elo_", "opp_elo_", "goals_", "opp_goals_", "xgp_", "opp_xgp_")) for v in stale
    )
    assert any(
        v.variable == "is_home" and v.status == "presente" for v in availability.variables
    )  # contexte : jamais périmé
    assert "football_data" in availability.reasons[0]


def test_excluded_match_h2_and_unknown_team(setup):
    matches, _, loaded = setup
    target = day_of(matches, lambda m: (m["api_league_id"] == 39) & (m["season_year"] == 2023))
    excluded = target.copy()
    excluded["excluded"] = True
    assert match_availability(excluded, pd.DataFrame(), loaded.model.features).status == EXCLUDED
    assert match_availability(target, pd.DataFrame(), loaded.model.features, horizon="H2").status == H2_UNAVAILABLE
    unknown = match_availability(target, pd.DataFrame(), loaded.model.features)
    assert unknown.status == UNAVAILABLE and "équipe inconnue" in unknown.reasons[0]


def test_sealed_dates_and_closed_replay_seasons_are_refused(setup, tmp_path):
    matches, _, loaded = setup
    ctx = context(matches, loaded, sealed_log=tmp_path / "journal.md")
    with pytest.raises(P.ReferenceDateRefused, match="scellés"):
        P.check_reference_date(dt.date(2025, 7, 1), "replay", ctx)
    with pytest.raises(P.ReferenceDateRefused, match="scellés"):
        P.check_reference_date(dt.date(2026, 10, 25), "live", ctx)
    with pytest.raises(P.ReferenceDateRefused, match="2021-22"):
        P.check_reference_date(dt.date(2020, 10, 3), "replay", ctx)
    P.check_reference_date(dt.date(2025, 6, 30), "replay", ctx)  # dernier jour ouvert


def test_live_refuses_past_days_with_a_simulated_today(setup):
    matches, _, loaded = setup
    upcoming = day_of(matches, lambda m: m["status"] != "played")
    ctx = context(matches, loaded, today=upcoming["match_day"])
    answers = P.predict_day(upcoming["match_day"], "live", ctx, match_ids=[upcoming["match_id"]])
    assert answers[0]["status"] == AVAILABLE and answers[0]["actual_score"] is None and answers[0]["mode"] == "live"
    with pytest.raises(P.ReferenceDateRefused, match="à venir"):
        P.predict_day(upcoming["match_day"] - dt.timedelta(days=1), "live", ctx)


def test_market_reference_only_for_unsealed_matches_with_odds(setup):
    matches, _, loaded = setup
    target = day_of(
        matches, lambda m: (m["api_league_id"] == 39) & (m["season_year"] == 2023) & (m["status"] == "played")
    )
    odds = pd.DataFrame({"match_id": [target["match_id"]], "version": ["avant_cloture"], "p_over": [0.55],
                         "odds_column": ["Avg"]})  # fmt: skip
    ctx = context(matches, loaded, odds=odds)
    (answer,) = P.predict_day(target["match_day"], "replay", ctx, match_ids=[target["match_id"]])
    assert answer["market_reference"] == {"p_over_2_5": 0.55, "odds_column": "Avg", "version": "avant_cloture"}
