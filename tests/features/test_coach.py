"""Entraîneur (G4, horizon H2) : ancienneté plafonnée, nouvel entraîneur, anti-fuite. Sans base."""

from __future__ import annotations

import datetime as dt

import numpy as np
import pandas as pd

from foot_predictor.features.coach import compute_coach

LEAGUE, CUP = 39, 45
DAY0 = dt.date(2018, 1, 1)


def match(mid, day, home=1, away=None, league=LEAGUE, status="played"):
    return {
        "match_id": mid,
        "match_day": DAY0 + dt.timedelta(days=day),
        "api_league_id": league,
        "home_team_id": home,
        "away_team_id": away if away is not None else 100 + mid,
        "status": status,
    }


def run(matches, coaches: dict[tuple[int, int], int | None]):
    """`coaches[(match, équipe)]` = identifiant API de l'entraîneur (None : inconnu)."""
    sheets = pd.DataFrame([{"match_id": m, "team_id": t, "api_coach_id": c} for (m, t), c in coaches.items()]).astype(
        {"api_coach_id": "Int64"}
    )
    return compute_coach(pd.DataFrame(matches), sheets)


def line(result, match_id, team=1):
    return result[(result["match_id"] == match_id) & (result["team_id"] == team)].iloc[0]


def season(n, step=7, coach=7):
    return [match(i, i * step) for i in range(1, n + 1)], {(i, 1): coach for i in range(1, n + 1)}


def test_first_observed_match_is_a_new_coach_with_zero_tenure():
    matches, coaches = season(1)
    row = line(run(matches, coaches), 1)
    assert row["coach_tenure_days"] == 0 and row["coach_is_new"] == 1


def test_tenure_counts_days_since_the_first_match_of_the_spell():
    matches, coaches = season(4)
    result = run(matches, coaches)
    assert line(result, 4)["coach_tenure_days"] == 21  # match 1 au jour 7, match 4 au jour 28


def test_new_coach_flag_ends_after_five_matches():
    matches, coaches = season(7)
    result = run(matches, coaches)
    flags = [line(result, i)["coach_is_new"] for i in range(1, 8)]
    assert flags == [1, 1, 1, 1, 1, 0, 0]  # 0 à 4 matchs antérieurs : nouveau ; 5 et plus : non


def test_tenure_is_capped_at_365_days():
    matches = [match(1, 0), match(2, 400)]
    row = line(run(matches, {(1, 1): 7, (2, 1): 7}), 2)
    assert row["coach_tenure_days"] == 365


def test_a_new_coach_restarts_the_spell():
    matches, coaches = season(8)
    coaches[(6, 1)] = coaches[(7, 1)] = coaches[(8, 1)] = 9
    result = run(matches, coaches)
    assert line(result, 6)["coach_tenure_days"] == 0 and line(result, 6)["coach_is_new"] == 1
    assert line(result, 8)["coach_tenure_days"] == 14 and line(result, 8)["coach_is_new"] == 1


def test_return_of_a_previous_coach_starts_again_from_zero():
    matches, coaches = season(9)
    for i in (4, 5, 6):
        coaches[(i, 1)] = 9
    row = line(run(matches, coaches), 7)  # 7 est de retour : le dernier match avait l'entraîneur 9
    assert row["coach_tenure_days"] == 0 and row["coach_is_new"] == 1


def test_unknown_coach_is_empty_and_leaves_the_history():
    matches, coaches = season(8)
    coaches[(3, 1)] = None
    result = run(matches, coaches)
    assert line(result, 3)[["coach_tenure_days", "coach_is_new"]].isna().all()
    assert (
        line(result, 4)["coach_tenure_days"] == 21
    )  # la période commence au match 1 (jour 7) ; 3 est seulement absent
    assert line(result, 4)["coach_is_new"] == 1  # 2 matchs connus avant lui


def test_unknown_coach_does_not_make_the_next_one_look_new():
    matches, coaches = season(8)
    coaches[(6, 1)] = None
    assert line(run(matches, coaches), 7)["coach_is_new"] == 0


def test_cup_and_unplayed_matches_stay_out_of_the_history():
    matches = [
        match(1, 0),
        match(2, 3, league=CUP),
        match(3, 4, status="scheduled"),
        match(4, 7),
    ]
    result = run(matches, {(1, 1): 7, (2, 1): 9, (3, 1): 9, (4, 1): 7})
    assert line(result, 4)["coach_tenure_days"] == 7  # ni la coupe ni le match non joué ne coupent la période
    assert 2 not in set(result["match_id"])
    assert np.isnan(line(result, 3)["coach_tenure_days"])


def test_history_is_limited_to_the_club():
    matches = [match(1, 0, home=1), match(2, 7, home=5)]
    result = run(matches, {(1, 1): 7, (2, 5): 7})  # le même entraîneur, mais au club 5 il arrive
    assert line(result, 2, 5)["coach_tenure_days"] == 0


def test_same_day_matches_do_not_see_each_other():
    matches = [match(1, 0, home=1), match(2, 7, home=1), match(3, 7, home=5)]
    result = run(matches, {(1, 1): 7, (2, 1): 7, (3, 5): 7})
    assert line(result, 3, 5)["coach_is_new"] == 1


def test_future_matches_never_change_a_value():
    matches, coaches = season(10)
    full = run(matches, coaches)
    truncated = run(matches[:6], {k: v for k, v in coaches.items() if k[0] <= 6})
    for mid in range(1, 7):
        pd.testing.assert_series_equal(
            line(full, mid)[["coach_tenure_days", "coach_is_new"]],
            line(truncated, mid)[["coach_tenure_days", "coach_is_new"]],
        )
    coaches[(10, 1)] = 99  # le dernier match change
    changed = run(matches, coaches)
    pd.testing.assert_series_equal(line(full, 9)[["coach_tenure_days"]], line(changed, 9)[["coach_tenure_days"]])


def test_columns_and_rows():
    matches, coaches = season(2)
    result = run(matches, coaches)
    assert list(result.columns) == ["match_id", "team_id", "is_home", "coach_tenure_days", "coach_is_new"]
    assert len(result) == 4  # une ligne par équipe, y compris l'adversaire sans feuille
    assert result[result["team_id"] > 100]["coach_tenure_days"].isna().all()
