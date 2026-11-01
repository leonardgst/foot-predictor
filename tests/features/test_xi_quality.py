"""Qualité du onze (G5, horizon H2) : rétrécissement, habituels absents, âge, anti-fuite. Sans base."""

from __future__ import annotations

import datetime as dt

import numpy as np
import pandas as pd
import pytest

from foot_predictor.features.xi_quality import compute_xi_quality, starter_quality

LEAGUE, CUP = 39, 45
K = 90.0
BASE = list(range(1, 12))


def match(mid, day, home, away, league=LEAGUE, status="played"):
    return {
        "match_id": mid,
        "match_day": dt.date.fromisoformat(day),
        "api_league_id": league,
        "home_team_id": home,
        "away_team_id": away,
        "status": status,
    }


def player(mid, team, pid, *, rating=6.0, minutes=90, bucket="Midfielder", birth="1995-01-01", stats_bucket=None):
    return {
        "match_id": mid,
        "team_id": team,
        "api_player_id": pid,
        "started": True,
        "position_bucket": bucket,
        "stats_position_bucket": stats_bucket,
        "rating": rating,
        "minutes": minutes,
        "birth_date": pd.Timestamp(birth) if birth else pd.NaT,
    }


def xi(mid, team, players=BASE, **kwargs):
    return [player(mid, team, p, **kwargs) for p in players]


def frames(rows, unknown=None):
    lineups = pd.DataFrame(rows)
    lineups["rating"] = lineups["rating"].astype("Float64")
    lineups["minutes"] = lineups["minutes"].astype("Int64")
    unknown = unknown or {}
    keys = lineups[["match_id", "team_id"]].drop_duplicates()
    sheets = keys.assign(
        unknown_starters=[unknown.get((m, t), 0) for m, t in zip(keys["match_id"], keys["team_id"], strict=True)],
        collision_excluded=0,
    )
    return lineups, sheets


def run(matches, rows, unknown=None, k=K):
    lineups, sheets = frames(rows, unknown)
    return compute_xi_quality(pd.DataFrame(matches), lineups, sheets, shrinkage_minutes=k)


def line(result, match_id, team):
    return result[(result["match_id"] == match_id) & (result["team_id"] == team)].iloc[0]


TWO = [match(1, "2018-09-01", 1, 2), match(2, "2018-09-08", 1, 3)]


def test_shrunk_rating_follows_the_formula():
    rows = [player(1, 1, p, rating=8.0 if p == 1 else 6.0) for p in BASE] + xi(2, 1)
    row = line(run(TWO, rows), 2, 1)
    mu = (8 * 90 + 10 * 6 * 90) / (11 * 90)
    expected = ((8 * 90 + K * mu) / (90 + K) + 10 * (6 * 90 + K * mu) / (90 + K)) / 11
    assert row["xi_quality"] == pytest.approx(expected)


def test_player_without_history_gets_the_position_mean_and_is_counted():
    rows = xi(1, 1, rating=7.0) + xi(2, 1, BASE[:10] + [99])
    table = starter_quality(*_for_starters(TWO, rows), shrinkage_minutes=K)
    new = table[table["player"] == 99].iloc[0]
    assert new["no_history"] and new["rated_minutes"] == 0
    assert new["quality"] == pytest.approx(7.0)  # μ du poste : tous les titulaires du match 1 ont 7
    assert table[table["match_id"] == 2]["no_history"].sum() == 1


def _for_starters(matches, rows):
    lineups, sheets = frames(rows)
    return pd.DataFrame(matches), lineups, sheets


def test_ratings_are_weighted_by_minutes():
    matches = [match(1, "2018-09-01", 1, 2), match(2, "2018-09-08", 1, 3), match(3, "2018-09-15", 1, 4)]
    rows = (
        [player(1, 1, p, rating=8.0 if p == 1 else 6.0) for p in BASE]
        + [player(2, 1, p, rating=4.0 if p == 1 else 6.0, minutes=10 if p == 1 else 90) for p in BASE]
        + xi(3, 1)
    )
    table = starter_quality(*_for_starters(matches, rows), shrinkage_minutes=K)
    first = table[(table["match_id"] == 3) & (table["player"] == 1)].iloc[0]
    assert first["rated_minutes"] == 100
    raw = (8 * 90 + 4 * 10) / 100
    mu = first["position_mean"]
    assert first["quality"] == pytest.approx((100 * raw + K * mu) / (100 + K))


def test_aberrant_ratings_and_minutes_are_ignored():
    rows = (
        [player(1, 1, 1, rating=2.0)]  # note hors de 3 à 10
        + [player(1, 1, 2, rating=8.0, minutes=200)]  # minutes hors de 1 à 130
        + [player(1, 1, p, rating=6.0) for p in BASE[2:]]
        + xi(2, 1)
    )
    table = starter_quality(*_for_starters(TWO, rows), shrinkage_minutes=K)
    second = table[table["match_id"] == 2].set_index("player")
    assert second.loc[1, "rated_minutes"] == 0 and second.loc[2, "rated_minutes"] == 0
    assert second.loc[3, "rated_minutes"] == 90
    assert second.loc[1, "position_mean"] == pytest.approx(6.0)  # les deux apparitions écartées ne pèsent pas dans μ


def test_first_match_has_no_quality_instead_of_a_default():
    """Rodage (D3) : sans note antérieure nulle part, la valeur est vide, jamais une constante."""
    row = line(run([TWO[0]], xi(1, 1)), 1, 1)
    assert np.isnan(row["xi_quality"])


def test_position_comes_from_the_history_when_the_lineup_lacks_it():
    rows = [player(1, 1, p, rating=8.0 if p == 1 else 5.0, bucket="Defender") for p in BASE]
    rows += [player(1, 2, 50 + i, rating=7.0, bucket="Attacker") for i in range(11)]
    rows += [player(2, 1, p, bucket=None) for p in BASE]
    row = starter_quality(*_for_starters(TWO, rows), shrinkage_minutes=K)
    row = row[row["match_id"] == 2]
    assert set(row["bucket"]) == {"Defender"}  # dernier poste connu de chaque joueur


def test_starter_without_any_position_leaves_the_row_empty():
    rows = xi(1, 1) + [player(2, 1, p, bucket=None if p == 99 else "Midfielder") for p in BASE[:10] + [99]]
    assert np.isnan(line(run(TWO, rows), 2, 1)["xi_quality"])


def test_statistics_position_is_used_for_past_appearances_only():
    rows = [player(1, 1, p, bucket=None, stats_bucket="Goalkeeper", rating=9.0) for p in BASE] + xi(2, 1)
    table = starter_quality(*_for_starters(TWO, rows), shrinkage_minutes=K)
    second = table[table["match_id"] == 2]
    assert set(second["bucket"]) == {"Midfielder"}  # le poste du match 2 vient de sa composition
    assert second["position_mean"].isna().all()  # personne n'a de note au poste Midfielder avant le match 2


def test_same_day_and_future_matches_never_change_a_value():
    matches = [match(1, "2018-09-01", 1, 2), match(2, "2018-09-08", 1, 3), match(3, "2018-09-08", 7, 8)]
    base_rows = xi(1, 1, rating=6.5) + xi(2, 1, rating=7.0) + xi(3, 7, list(range(21, 32)), rating=9.9)
    first = line(run(matches, base_rows), 2, 1)
    # la note du match 2 lui-même et celle du match du même jour changent : sa valeur reste la même
    other = xi(1, 1, rating=6.5) + xi(2, 1, rating=3.5) + xi(3, 7, list(range(21, 32)), rating=3.5)
    assert line(run(matches, other), 2, 1)["xi_quality"] == pytest.approx(first["xi_quality"])
    # un match postérieur ne change rien non plus
    later = matches + [match(4, "2018-09-15", 1, 4)]
    extended = base_rows + xi(4, 1, rating=3.0)
    columns = ["xi_quality", "xi_regulars_missing", "xi_mean_age"]
    pd.testing.assert_series_equal(line(run(later, extended), 2, 1)[columns], first[columns])


def test_cup_and_unplayed_matches_stay_out_of_the_history():
    matches = [
        match(1, "2018-09-01", 1, 2),
        match(2, "2018-09-05", 1, 3, league=CUP),
        match(3, "2018-09-06", 1, 4, status="scheduled"),
        match(4, "2018-09-08", 1, 5),
    ]
    rows = xi(1, 1, rating=7.0) + xi(2, 1, rating=3.0) + xi(3, 1, rating=3.0) + xi(4, 1, rating=7.0)
    result = run(matches, rows)
    assert line(result, 4, 1)["xi_quality"] == pytest.approx(7.0)
    assert 2 not in set(result["match_id"])
    assert np.isnan(line(result, 3, 1)["xi_quality"])  # match non joué


def test_incomplete_xi_is_empty():
    rows = xi(1, 1) + xi(2, 1, BASE[:10])
    result = run(TWO, rows, unknown={(2, 1): 1})
    assert line(result, 2, 1)[["xi_quality", "xi_regulars_missing", "xi_mean_age"]].isna().all()


def test_mean_age_in_years_at_match_day():
    rows = xi(1, 1) + [player(2, 1, p, birth="1998-09-08" if p <= 6 else "1988-09-08") for p in BASE]
    row = line(run(TWO, rows), 2, 1)
    assert row["xi_mean_age"] == pytest.approx((6 * 20 + 5 * 30) / 11, abs=0.05)


def test_mean_age_is_empty_when_a_birth_date_is_missing():
    rows = xi(1, 1) + [player(2, 1, p, birth=None if p == 3 else "1995-01-01") for p in BASE]
    row = line(run(TWO, rows), 2, 1)
    assert np.isnan(row["xi_mean_age"])
    assert not np.isnan(row["xi_quality"])  # les autres variables ne dépendent pas de l'âge


def _season(n_history, last_xi, history_xi=BASE):
    matches = [
        match(i, f"2018-{(i - 1) // 28 + 1:02d}-{(i - 1) % 28 + 1:02d}", 1, 100 + i) for i in range(1, n_history + 2)
    ]
    rows = []
    for i in range(1, n_history + 1):
        rows += xi(i, 1, history_xi)
    rows += xi(n_history + 1, 1, last_xi)
    return matches, rows


def test_regulars_missing_is_the_share_of_regulars_absent():
    matches, rows = _season(10, BASE[:9] + [50, 51])  # deux habituels (10 et 11) remplacés
    row = line(run(matches, rows), 11, 1)
    assert row["xi_regulars_missing"] == pytest.approx(2 / 11)
    matches, rows = _season(10, BASE)
    assert line(run(matches, rows), 11, 1)["xi_regulars_missing"] == 0.0


def test_regulars_need_five_starts_in_the_last_ten():
    matches = [match(i, f"2018-09-{i:02d}", 1, 100 + i) for i in range(1, 12)]
    rows = []
    for i in range(1, 11):
        # le joueur 11 débute 4 matchs sur 10 (pas un habituel) ; le joueur 12 en débute 6 (un habituel)
        rows += xi(i, 1, BASE[:9] + ([11] if i <= 4 else [12]) + [10])
    rows += xi(11, 1, BASE[:9] + [10, 13])
    row = line(run(matches, rows), 11, 1)
    # habituels : 1..10 (10 débuts) et 12 (6 débuts) ; 11 (4 débuts) n'en est pas un ; seul 12 est absent
    assert row["xi_regulars_missing"] == pytest.approx(1 / 11)


def test_regulars_missing_is_empty_with_fewer_than_ten_matches():
    matches, rows = _season(9, BASE)
    assert np.isnan(line(run(matches, rows), 10, 1)["xi_regulars_missing"])


def test_one_row_per_team_and_match_and_h1_columns_absent():
    result = run([match(1, "2018-09-01", 1, 2)], xi(1, 1) + xi(1, 2, list(range(21, 32))))
    assert len(result) == 2
    assert list(result.columns) == [
        "match_id",
        "team_id",
        "is_home",
        "xi_quality",
        "xi_regulars_missing",
        "xi_mean_age",
    ]
