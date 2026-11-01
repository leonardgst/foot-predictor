"""Stabilité du onze (G6, horizon H2) : définitions, égalité matrice = recouvrement, anti-fuite. Sans base."""

from __future__ import annotations

import datetime as dt

import numpy as np
import pandas as pd
import pytest

from foot_predictor.features.lineup_stability import (
    HALF_LIVES,
    common_starters,
    compute_lineup_stability,
    pair_score,
)

LEAGUE, CUP = 39, 45


def match(mid, day, home, away, league=LEAGUE, status="played"):
    return {
        "match_id": mid,
        "match_day": dt.date.fromisoformat(day),
        "api_league_id": league,
        "home_team_id": home,
        "away_team_id": away,
        "status": status,
    }


def sheets_and_lineups(xis: dict[tuple[int, int], list[int]], unknown: dict[tuple[int, int], int] | None = None):
    """Feuilles et compositions : `xis[(match, équipe)]` = identifiants API des titulaires."""
    unknown = unknown or {}
    lineups = [
        {"match_id": m, "team_id": t, "api_player_id": p, "started": True}
        for (m, t), players in xis.items()
        for p in players
    ]
    sheets = [
        {"match_id": m, "team_id": t, "unknown_starters": unknown.get((m, t), 0), "collision_excluded": 0}
        for (m, t) in xis
    ]
    return pd.DataFrame(lineups), pd.DataFrame(sheets)


def line(result, match_id, team):
    return result[(result["match_id"] == match_id) & (result["team_id"] == team)].iloc[0]


def run(matches, xis, unknown=None):
    lineups, sheets = sheets_and_lineups(xis, unknown)
    return compute_lineup_stability(pd.DataFrame(matches), lineups, sheets)


BASE = list(range(1, 12))


def test_matrix_equals_overlap_on_random_lineups():
    """H.3 : la somme de la matrice cumulée restreinte au onze vaut Σ s_k(s_k − 1)."""
    rng = np.random.default_rng(20260930)
    n_players, n_matches = 30, 25
    xi = np.zeros((n_matches, n_players))
    for k in range(n_matches):
        xi[k, rng.choice(n_players, 11, replace=False)] = 1.0
    common = common_starters(xi)
    for m in range(1, n_matches):
        cumulated = sum(np.outer(xi[k], xi[k]) - np.diag(xi[k]) for k in range(m))  # matrice des paires, diagonale à 0
        by_matrix = xi[m] @ cumulated @ xi[m]
        by_overlap = float((common[m, :m] * (common[m, :m] - 1)).sum())
        assert by_matrix == pytest.approx(by_overlap)
        assert by_matrix / (110 * m) == pytest.approx(pair_score(common)[m, :m].mean())


def test_identical_lineup_gives_overlap_and_cohesion_of_one():
    matches = [match(1, "2018-09-01", 1, 2), match(2, "2018-09-08", 1, 3)]
    result = run(matches, {(1, 1): BASE, (2, 1): BASE})
    row = line(result, 2, 1)
    assert row["xi_overlap_prev"] == 11
    assert all(row[f"xi_cohesion_ewm_h{h}"] == pytest.approx(1.0) for h in ("3", "5", "10", "20", "inf"))


def test_first_match_has_no_value_instead_of_one():
    """H.2 : sans match antérieur, la valeur est vide, jamais 1 ni 0."""
    result = run([match(1, "2018-09-01", 1, 2)], {(1, 1): BASE})
    row = line(result, 1, 1)
    assert row[["xi_overlap_prev", "xi_cohesion_ewm_hinf", "xi_new_starters"]].isna().all()


def test_overlap_counts_common_starters_with_previous_match_only():
    matches = [match(1, "2018-09-01", 1, 2), match(2, "2018-09-08", 1, 3), match(3, "2018-09-15", 1, 4)]
    xis = {(1, 1): BASE, (2, 1): BASE[:8] + [21, 22, 23], (3, 1): BASE[:8] + [21, 22, 23]}
    result = run(matches, xis)
    assert line(result, 2, 1)["xi_overlap_prev"] == 8
    assert line(result, 3, 1)["xi_overlap_prev"] == 11


def test_cohesion_weights_decay_by_match_rank():
    matches = [match(1, "2018-09-01", 1, 2), match(2, "2018-09-08", 1, 3), match(3, "2018-09-15", 1, 4)]
    xis = {(1, 1): BASE, (2, 1): BASE[:9] + [21, 22], (3, 1): BASE}
    row = line(run(matches, xis), 3, 1)
    # s avec le match 2 : 9 ; avec le match 1 : 11. Le match 2 est le plus récent (rang 1).
    f2, f1 = 9 * 8 / 110, 1.0
    assert row["xi_cohesion_ewm_hinf"] == pytest.approx((f2 + f1) / 2)
    w = 0.5 ** (1 / 3)
    assert row["xi_cohesion_ewm_h3"] == pytest.approx((f2 + w * f1) / (1 + w))


def test_no_reset_across_seasons_and_club_only():
    matches = [match(1, "2018-05-01", 1, 2), match(2, "2018-08-20", 1, 3), match(3, "2018-08-20", 5, 6)]
    xis = {(1, 1): BASE, (2, 1): BASE, (3, 5): BASE}  # l'équipe 5 aligne les mêmes joueurs, mais n'a aucun passé
    result = run(matches, xis)
    assert line(result, 2, 1)["xi_overlap_prev"] == 11  # traverse l'intersaison
    assert np.isnan(line(result, 3, 5)["xi_overlap_prev"])  # l'historique d'un autre club ne compte pas


def test_new_starters_use_the_last_365_days_and_three_starts():
    matches = [match(i, f"2018-0{i}-01", 1, 2) for i in range(1, 5)] + [match(9, "2018-09-01", 1, 2)]
    veteran = list(range(1, 11))
    xis = {(i, 1): veteran + [50 + i] for i in range(1, 5)}  # les 10 premiers jouent 4 fois ; le 11e change
    xis[(9, 1)] = veteran + [99]
    row = line(run(matches, xis), 9, 1)
    assert row["xi_new_starters"] == 1  # seul 99 a moins de 3 titularisations
    xis[(9, 1)] = [1, 2, 3, 4, 5, 6, 7, 8, 9, 98, 99]
    assert line(run(matches, xis), 9, 1)["xi_new_starters"] == 2


def test_starts_older_than_365_days_do_not_count():
    matches = [match(i, d, 1, 2) for i, d in enumerate(["2016-01-01", "2016-02-01", "2016-03-01", "2018-09-01"], 1)]
    xis = {(i, 1): BASE for i in (1, 2, 3, 4)}
    assert line(run(matches, xis), 4, 1)["xi_new_starters"] == 11


def test_cup_and_unplayed_matches_stay_out_of_the_history():
    matches = [
        match(1, "2018-09-01", 1, 2),
        match(2, "2018-09-05", 1, 3, league=CUP),
        match(3, "2018-09-06", 1, 4, status="scheduled"),
        match(4, "2018-09-08", 1, 5),
    ]
    xis = {(1, 1): BASE, (2, 1): list(range(31, 42)), (3, 1): list(range(51, 62)), (4, 1): BASE}
    result = run(matches, xis)
    assert line(result, 4, 1)["xi_overlap_prev"] == 11  # le match de coupe et le match non joué sont ignorés
    assert 2 not in set(result["match_id"])


def test_incomplete_xi_is_empty_and_leaves_the_history():
    matches = [match(1, "2018-09-01", 1, 2), match(2, "2018-09-08", 1, 3), match(3, "2018-09-15", 1, 4)]
    xis = {(1, 1): BASE, (2, 1): BASE[:10], (3, 1): BASE}  # 10 titulaires identifiés au match 2
    result = run(matches, xis, unknown={(2, 1): 1})
    assert (
        result[(result["match_id"] == 2) & (result["team_id"] == 1)]
        .iloc[0]
        .drop(["match_id", "team_id", "is_home"])
        .isna()
        .all()
    )
    assert line(result, 3, 1)["xi_overlap_prev"] == 11  # le match 3 compare avec le match 1


def test_future_matches_never_change_a_value():
    """Anti-fuite : modifier ou retirer un match postérieur ne change pas la valeur du match évalué."""
    matches = [match(i, f"2018-0{i}-10", 1, 2) for i in range(1, 7)]
    rng = np.random.default_rng(1)
    xis = {(i, 1): [int(p) for p in rng.choice(20, 11, replace=False)] for i in range(1, 7)}
    full = run(matches, xis)
    truncated = run(matches[:4], {k: v for k, v in xis.items() if k[0] <= 4})
    columns = [c for c in full.columns if c.startswith("xi_")]
    for mid in (1, 2, 3, 4):
        a, b = line(full, mid, 1)[columns], line(truncated, mid, 1)[columns]
        pd.testing.assert_series_equal(a, b)
    xis[(6, 1)] = list(range(70, 81))  # le dernier match change
    changed = run(matches, xis)
    pd.testing.assert_series_equal(line(full, 5, 1)[columns], line(changed, 5, 1)[columns])


def test_same_day_matches_do_not_see_each_other():
    matches = [match(1, "2018-09-01", 1, 2), match(2, "2018-09-08", 1, 3), match(3, "2018-09-08", 7, 8)]
    result = run(matches, {(1, 1): BASE, (2, 1): BASE, (3, 7): BASE})
    assert np.isnan(line(result, 3, 7)["xi_overlap_prev"])


def test_one_cohesion_column_per_half_life():
    result = run([match(1, "2018-09-01", 1, 2)], {(1, 1): BASE})
    assert len([c for c in result.columns if c.startswith("xi_cohesion_ewm_h")]) == len(HALF_LIVES)
