"""Glissants (G2) et xg_proxy : règle temporelle, ancienneté, décroissance en jours. Sans base."""

from __future__ import annotations

import datetime as dt

import numpy as np
import pandas as pd
import pytest

from foot_predictor.features import xg_proxy
from foot_predictor.features.rolling import compute_rolling

COEF = xg_proxy.XgProxyCoefficients(on_target=0.3, off_target=0.05, n_team_matches=0, seasons="test")


def match(mid, day, home, away, hg, ag, shots=(10, 8, 4, 3), status="played", excluded=False, league=39, comp=1):
    hs, as_, hst, ast = shots
    return {
        "match_id": mid,
        "match_day": dt.date.fromisoformat(day),
        "competition_id": comp,
        "api_league_id": league,
        "home_team_id": home,
        "away_team_id": away,
        "home_goals_90": hg,
        "away_goals_90": ag,
        "status": status,
        "excluded": excluded,
        "home_shots_fd": hs,
        "away_shots_fd": as_,
        "home_sot_fd": hst,
        "away_sot_fd": ast,
    }


def run(rows, **kwargs):
    return compute_rolling(pd.DataFrame(rows), COEF, half_lives=(60,), **kwargs)


def row(result, match_id, team):
    return result[(result["match_id"] == match_id) & (result["team_id"] == team)].iloc[0]


def test_team_without_history_stays_empty_never_zero():
    result = run([match(1, "2020-08-01", 1, 2, 2, 0)])
    first = row(result, 1, 1)
    assert first["goals_weight_h60"] == 0
    assert np.isnan(first["goals_for_ewm_h60"]) and np.isnan(first["xgp_for_ewm_h60"])
    assert np.isnan(first["days_since_last_league_match"])


def test_changing_the_result_of_m_does_not_change_the_row_of_m():
    rows = [match(1, "2020-08-01", 1, 2, 2, 0), match(2, "2020-08-08", 1, 3, 1, 1), match(3, "2020-08-08", 2, 3, 0, 0)]
    before = run(rows)
    rows[1] = match(2, "2020-08-08", 1, 3, 9, 0, shots=(30, 1, 20, 0))
    after = run(rows)
    pd.testing.assert_series_equal(row(before, 2, 1), row(after, 2, 1))


def test_shrinkage_formula_and_day_decay():
    """Deux matchs passés à 10 et 100 jours : poids 0,5^(10/60) et 0,5^(100/60), retrait vers μ."""
    rows = [
        match(1, "2020-01-01", 1, 2, 3, 1),  # J − 100 pour le match 3
        match(2, "2020-03-31", 1, 2, 1, 1),  # J − 10
        match(3, "2020-04-10", 1, 2, 0, 0),
    ]
    result = run(rows)
    w1, w2 = 0.5 ** (100 / 60), 0.5 ** (10 / 60)
    mu = (3 + 1 + 1 + 1) / 4  # buts par équipe-match du championnat avant le jour J
    expected = (w1 * 3 + w2 * 1 + 3 * mu) / (w1 + w2 + 3)
    target = row(result, 3, 1)
    assert target["goals_weight_h60"] == pytest.approx(w1 + w2)
    assert target["goals_for_ewm_h60"] == pytest.approx(expected)
    assert target["days_since_last_league_match"] == 10


def test_summer_break_counts():
    """Même équipe, même dernier résultat : un match de mai pèse moins en août qu'en juin."""
    early = run([match(1, "2020-05-20", 1, 2, 3, 0), match(2, "2020-06-01", 1, 2, 0, 0)])
    late = run([match(1, "2020-05-20", 1, 2, 3, 0), match(2, "2020-08-20", 1, 2, 0, 0)])
    assert row(early, 2, 1)["goals_weight_h60"] > row(late, 2, 1)["goals_weight_h60"]


def test_matches_older_than_the_maximum_age_are_ignored():
    rows = [match(1, "2018-01-01", 1, 2, 5, 0), match(2, "2020-06-01", 1, 2, 0, 0)]
    result = run(rows)
    assert row(result, 2, 1)["goals_weight_h60"] == 0
    assert np.isnan(row(result, 2, 1)["goals_for_ewm_h60"])
    kept = run(rows, max_age=1000)
    assert row(kept, 2, 1)["goals_weight_h60"] > 0


def test_no_reset_at_the_change_of_season():
    """Le match de la saison précédente reste dans la moyenne (aucune colonne saison n'est lue)."""
    rows = [match(1, "2020-05-20", 1, 2, 2, 0), match(2, "2020-09-12", 1, 3, 0, 0)]
    assert row(run(rows), 2, 1)["goals_weight_h60"] == pytest.approx(0.5 ** (115 / 60))


def test_same_day_matches_do_not_influence_each_other():
    rows = [match(1, "2020-08-01", 1, 2, 4, 0), match(2, "2020-08-01", 1, 3, 0, 4)]
    result = run(rows)
    assert row(result, 2, 1)["goals_weight_h60"] == 0


def test_unplayed_or_excluded_matches_never_feed_the_history():
    rows = [
        match(1, "2020-08-01", 1, 2, 4, 0, excluded=True),
        match(2, "2020-08-02", 1, 2, None, None, status="scheduled"),
        match(3, "2020-08-09", 1, 2, 1, 0),
    ]
    assert row(run(rows), 3, 1)["goals_weight_h60"] == 0


def test_missing_shots_leave_xgp_empty_but_goals_computed():
    rows = [match(1, "2020-08-01", 1, 2, 1, 0, shots=(None, None, None, None)), match(2, "2020-08-08", 1, 2, 0, 0)]
    target = row(run(rows), 2, 1)
    assert target["goals_weight_h60"] > 0 and target["xgp_weight_h60"] == 0
    assert np.isnan(target["xgp_for_ewm_h60"])


def test_xgp_for_and_against_come_from_each_side():
    rows = [match(1, "2020-08-01", 1, 2, 1, 0, shots=(10, 6, 4, 2)), match(2, "2020-08-08", 1, 2, 0, 0)]
    result = run(rows)
    for_1 = 0.3 * 4 + 0.05 * 6
    against_1 = 0.3 * 2 + 0.05 * 4
    w = 0.5 ** (7 / 60)
    mu = (for_1 + against_1) / 2
    assert row(result, 2, 1)["xgp_for_ewm_h60"] == pytest.approx((w * for_1 + 3 * mu) / (w + 3))
    assert row(result, 2, 2)["xgp_for_ewm_h60"] == pytest.approx((w * against_1 + 3 * mu) / (w + 3))


def test_xg_proxy_estimation_refuses_validation_seasons():
    with pytest.raises(ValueError):
        xg_proxy.estimate(pd.DataFrame(), seasons=range(2015, 2022))


def test_xg_proxy_estimation_recovers_known_coefficients():
    rng = np.random.default_rng(0)
    n = 4000
    on = rng.integers(0, 10, n)
    off = rng.integers(0, 12, n)
    goals = 0.3 * on + 0.04 * off + rng.normal(0, 0.05, n)
    frame = pd.DataFrame(
        {
            "match_id": np.arange(n),
            "season_year": 2016,
            "api_league_id": 39,
            "status": "played",
            "excluded": False,
            "home_team_id": 1,
            "away_team_id": 2,
            "home_goals_90": goals,
            "away_goals_90": goals,
            "home_shots_fd": on + off,
            "away_shots_fd": on + off,
            "home_sot_fd": on,
            "away_sot_fd": on,
        }
    )
    coef = xg_proxy.estimate(frame)
    assert coef.on_target == pytest.approx(0.3, abs=0.01) and coef.off_target == pytest.approx(0.04, abs=0.01)


def test_xg_proxy_apply_is_empty_when_a_value_is_missing_or_incoherent():
    values = xg_proxy.apply(COEF, [10, None, 3], [4, 2, 5])
    assert values.iloc[0] == pytest.approx(0.3 * 4 + 0.05 * 6)
    assert pd.isna(values.iloc[1]) and pd.isna(values.iloc[2])


def test_xg_proxy_coefficients_are_never_negative():
    """Estimation contrainte : un tir ne retire jamais de but attendu (b ≥ 0 même si l'estimation libre est < 0)."""
    rng = np.random.default_rng(2)
    n = 3000
    on = rng.integers(0, 10, n)
    off = rng.integers(0, 12, n)
    goals = 0.3 * on - 0.02 * off + rng.normal(0, 0.05, n)
    frame = pd.DataFrame(
        {
            "match_id": np.arange(n), "season_year": 2017, "api_league_id": 39, "status": "played", "excluded": False,
            "home_team_id": 1, "away_team_id": 2, "home_goals_90": goals, "away_goals_90": goals,
            "home_shots_fd": on + off, "away_shots_fd": on + off, "home_sot_fd": on, "away_sot_fd": on,
        }
    )  # fmt: skip
    assert xg_proxy.estimate(frame, nonnegative=False).off_target < 0
    constrained = xg_proxy.estimate(frame)
    assert constrained.off_target == 0 and constrained.on_target > 0
