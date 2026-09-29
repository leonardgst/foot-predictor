"""Elo maison (G1) : théorie, mise à jour par jour, intersaison, équipes promues. Sans base."""

from __future__ import annotations

import datetime as dt

import pandas as pd
import pytest

from foot_predictor.features.elo import EloParams, compute_elo, expected_home, goal_factor

PARAMS = EloParams(k=20, home_advantage=60, season_regression=0.5, goal_multiplier=True, initial_gap=100)
EPL, CHAMP = 39, 40  # une échelle : Angleterre, D1 et D2


def match(mid, day, home, away, hg, ag, league=EPL, season=2000, status="played", excluded=False, round_=None):
    return {
        "match_id": mid,
        "match_day": dt.date.fromisoformat(day),
        "season_year": season,
        "api_league_id": league,
        "home_team_id": home,
        "away_team_id": away,
        "home_goals_90": hg,
        "away_goals_90": ag,
        "status": status,
        "excluded": excluded,
        "round": round_ or "Regular Season - 1",
    }


def frame(*rows):
    return pd.DataFrame(list(rows))


def ratings(result, team, match_id):
    row = result[(result["team_id"] == team) & (result["match_id"] == match_id)].iloc[0]
    return row["elo_pre"], row["opp_elo_pre"], row["elo_matches"]


def test_goal_factor_follows_the_national_teams_elo():
    assert [goal_factor(n) for n in (0, 1, 2, 3, 4)] == [1, 1, 1.5, 14 / 8, 15 / 8]
    assert goal_factor(5, enabled=False) == 1


def test_expected_score_is_symmetric():
    assert expected_home(1500, 1500, 0) == pytest.approx(0.5)
    assert expected_home(1600, 1500, 60) + expected_home(1500, 1600, -60) == pytest.approx(1.0)


def test_a_win_raises_the_rating_and_the_update_is_zero_sum():
    result = compute_elo(frame(match(1, "2000-08-01", 1, 2, 2, 0), match(2, "2000-08-08", 1, 2, 0, 0)), PARAMS)
    home_pre, away_pre, _ = ratings(result, 1, 2)
    assert home_pre > 1500 > away_pre
    assert home_pre + away_pre == pytest.approx(3000)  # somme nulle


def test_first_ratings_by_division():
    result = compute_elo(frame(match(1, "2000-08-01", 1, 2, 1, 0), match(2, "2000-08-01", 3, 4, 1, 0, league=CHAMP)))
    assert ratings(result, 1, 1)[0] == 1500
    assert ratings(result, 3, 2)[0] == 1500 - EloParams().initial_gap


def test_two_matches_on_the_same_day_do_not_influence_each_other():
    """L'équipe 1 joue deux fois le même jour : ses deux notes d'avant-match sont identiques."""
    rows = frame(
        match(1, "2000-08-01", 1, 2, 3, 0), match(2, "2000-08-01", 1, 3, 0, 1), match(3, "2000-08-05", 1, 2, 0, 0)
    )
    result = compute_elo(rows, PARAMS)
    assert ratings(result, 1, 1)[0] == ratings(result, 1, 2)[0] == 1500
    # Le lendemain, les deux variations sont appliquées ensemble.
    expected = 1500 + 20 * 14 / 8 * (1 - expected_home(1500, 1500, 60)) + 20 * 1 * (0 - expected_home(1500, 1500, 60))
    assert ratings(result, 1, 3)[0] == pytest.approx(expected)
    assert ratings(result, 1, 3)[2] == 2


def test_row_order_does_not_matter():
    rows = frame(
        match(1, "2000-08-01", 1, 2, 2, 1),
        match(2, "2000-08-01", 3, 4, 0, 0),
        match(3, "2000-08-09", 1, 3, 1, 1),
        match(4, "2000-08-09", 2, 4, 0, 3),
    )
    a = compute_elo(rows, PARAMS).sort_values(["match_id", "team_id"]).reset_index(drop=True)
    b = compute_elo(rows.iloc[::-1], PARAMS).sort_values(["match_id", "team_id"]).reset_index(drop=True)
    pd.testing.assert_frame_equal(a, b)


def test_changing_a_result_does_not_change_that_match_ratings():
    rows = frame(match(1, "2000-08-01", 1, 2, 2, 1), match(2, "2000-08-09", 1, 2, 0, 0))
    before = compute_elo(rows, PARAMS)
    rows.loc[1, ["home_goals_90", "away_goals_90"]] = [7, 0]
    after = compute_elo(rows, PARAMS)
    assert ratings(before, 1, 2) == ratings(after, 1, 2)


def test_unplayed_and_excluded_matches_get_ratings_but_do_not_update():
    rows = frame(
        match(1, "2000-08-01", 1, 2, 5, 0, excluded=True),
        match(2, "2000-08-02", 1, 2, None, None, status="scheduled"),
        match(3, "2000-08-09", 1, 2, 0, 0),
    )
    result = compute_elo(rows, PARAMS)
    assert ratings(result, 1, 2)[0] == 1500 and ratings(result, 1, 3)[0] == 1500
    assert ratings(result, 1, 3)[2] == 0


def test_season_regression_towards_the_division_mean():
    rows = frame(match(1, "2000-08-01", 1, 2, 4, 0), match(2, "2001-08-01", 1, 2, 0, 0, season=2001))
    result = compute_elo(rows, PARAMS)
    end_1 = 1500 + 20 * (11 + 4) / 8 * (1 - expected_home(1500, 1500, 60))
    end_2 = 3000 - end_1
    mean = (end_1 + end_2) / 2
    assert ratings(result, 1, 2)[0] == pytest.approx(mean + 0.5 * (end_1 - mean))
    assert ratings(result, 2, 2)[0] == pytest.approx(mean + 0.5 * (end_2 - mean))


def test_promoted_team_without_history_gets_the_entry_rating():
    """Équipe 9, jamais vue, qui entre en D2 : moyenne des 3 plus basses notes de fin de D2."""
    season_2000 = [
        match(1, "2001-03-01", 11, 12, 3, 0, league=CHAMP),
        match(2, "2001-03-01", 13, 14, 2, 0, league=CHAMP),
        match(3, "2001-03-01", 15, 16, 1, 1, league=CHAMP),
    ]
    rows = frame(*season_2000, match(4, "2001-08-10", 9, 11, 0, 0, league=CHAMP, season=2001))
    result = compute_elo(rows, PARAMS)
    base = 1500 - 100
    deltas = [20 * 14 / 8 * (1 - expected_home(base, base, 60)), 20 * 1.5 * (1 - expected_home(base, base, 60)),
              20 * (0.5 - expected_home(base, base, 60))]  # fmt: skip
    end = {11: base + deltas[0], 12: base - deltas[0], 13: base + deltas[1], 14: base - deltas[1],
           15: base + deltas[2], 16: base - deltas[2]}  # fmt: skip
    lowest = sorted(end.values())[:3]
    assert ratings(result, 9, 4)[0] == pytest.approx(sum(lowest) / 3)


def test_a_playoff_does_not_move_a_d2_team_into_the_d1_means():
    """Barrage de D1 joué par une équipe de D2 : son niveau de la saison reste la D2."""
    rows = frame(
        match(1, "2001-03-01", 1, 2, 1, 0),  # D1
        match(2, "2001-03-01", 3, 4, 1, 0, league=CHAMP),  # D2
        match(3, "2001-05-20", 2, 3, 0, 1, round_="Relegation Round"),  # barrage dans la compétition de D1
        match(4, "2001-08-10", 1, 2, 0, 0, season=2001),
    )
    result = compute_elo(rows, PARAMS)
    d1 = 20 * (1 - expected_home(1500, 1500, 60))
    d2 = 20 * (1 - expected_home(1400, 1400, 60))
    playoff = 20 * (0 - expected_home(1500 - d1, 1400 + d2, 60))  # variation de l'équipe 2, à domicile
    d1_mean = ((1500 + d1) + (1500 - d1 + playoff)) / 2  # équipes 1 et 2 seulement, pas l'équipe 3
    home, away, _ = ratings(result, 1, 4)
    assert (home + away) / 2 == pytest.approx(d1_mean)


def test_tuning_refuses_any_season_after_2014_15():
    from foot_predictor.features.elo_tuning import tune

    with pytest.raises(ValueError):
        tune(frame(match(1, "2015-08-08", 1, 2, 1, 0, season=2015)))


def test_ordered_logit_recovers_a_known_model():
    import numpy as np
    from scipy.special import expit

    from foot_predictor.features.elo_tuning import ordered_logit_log_loss

    rng = np.random.default_rng(1)
    x = rng.normal(0, 0.5, 20000)
    beta, c1, c2 = 1.5, -0.7, 0.4
    u = rng.random(len(x))
    y = np.where(u < expit(c1 - beta * x), 0, np.where(u < expit(c2 - beta * x), 1, 2))
    _, theta = ordered_logit_log_loss(x, y)
    assert theta == pytest.approx([beta, c1, c2], abs=0.08)
