"""Détection partagée des collisions : mêmes résultats que raw_check (sans le modifier), et option 2b."""

from __future__ import annotations

from foot_predictor.ingestion import collisions as col
from foot_predictor.quality import raw_check
from foot_predictor.quality.raw_check import RawChecker
from tests.quality.test_raw_check import NOW, build_multi, profile, synthetic


def lineup(team, players):
    return {
        "team": {"id": team},
        "startXI": [{"player": {"id": p, "number": n}} for p, n in players],
        "substitutes": [],
    }


def stats(team, players):
    return {
        "team": {"id": team},
        "players": [{"player": {"id": p}, "statistics": [{"games": {"number": n}}]} for p, n in players],
    }


def test_normal_presence_takes_the_lineup_team():
    result = col.classify_match([lineup(1, [(10, 7)])], [stats(1, [(10, 7)])])
    assert result.team == {10: 1} and not result.collisions and not result.false_positives


def test_same_team_collision_resolved_by_the_lineup_number():
    result = col.classify_match([lineup(1, [(10, 7)])], [stats(1, [(10, 7), (10, 8)])])
    assert result.collisions == {10: col.SAME_TEAM}
    assert result.resolved_number(10) == 7


def test_same_team_collision_unresolved_when_two_numbers_in_the_lineup():
    result = col.classify_match([lineup(1, [(10, 7), (10, 8)])], [stats(1, [(10, 7)])])
    assert result.collisions == {10: col.SAME_TEAM}
    assert result.resolved_number(10) is None


def test_two_teams_is_never_resolved():
    result = col.classify_match([lineup(1, [(10, 7)]), lineup(2, [(10, 7)])], [])
    assert result.collisions == {10: col.TWO_TEAMS} and result.resolved_number(10) is None


def test_swapped_stats_keep_the_lineup_team():
    home, away = [(p, p) for p in range(51, 56)], [(p, p) for p in range(61, 66)]
    result = col.classify_match([lineup(1, home), lineup(2, away)], [stats(1, away), stats(2, home)])
    assert not result.collisions
    assert all(result.team[p] == 1 for p, _ in home)
    assert set(result.false_positives.values()) == {col.SWAPPED_STATS}


def test_unknown_id_is_counted_not_classified():
    result = col.classify_match([lineup(1, [(0, 1), (None, 2)])], [stats(1, [(0, 1)])])
    assert result.unknown_entries == 2 and not result.places


def test_same_day_collisions():
    # joueur 5 : équipe 1 (match 100) et équipe 2 (match 200) le même jour ; joueur 6 : même équipe deux fois.
    found = col.same_day_collisions([5, 5, 6, 6], [10, 10, 10, 10], [1, 2, 1, 1], [100, 200, 100, 300])
    assert found == {(5, 100), (5, 200)}
    assert col.same_day_collisions([], [], [], []) == set()


def test_retained_birth():
    assert col.retained_birth({"1990-01-01": {2015}}) == "1990-01-01"
    assert col.retained_birth({"1990-01-01": {2015}, "1990-01-10": {2017}}) == "1990-01-10"  # correction
    assert col.retained_birth({"1990-01-01": {2015, 2017}, "1990-01-10": {2016}}) is None  # collision
    assert col.retained_birth({}) is None


def test_same_results_as_raw_check(tmp_path, multi_config):
    """Équivalence avec raw_check sur un brut synthétique qui réunit tous les cas."""
    raw = tmp_path / "raw"
    swapped_home, swapped_away = [51, 52, 53, 54, 55, 56], [61, 62, 63]
    p1 = [
        synthetic(1001, "2015-08-15", 1, 2, [601, 11, 501], [601, 21]),
        synthetic(1002, "2015-08-22", 1, 2, [12, 602], [22], home_stats=[12, 602, 602]),
        synthetic(1003, "2015-08-29", 1, 2, [(603, 4), 13], [23], home_stats=[(603, 4), (603, 5), 13]),
        synthetic(1004, "2015-09-05", 1, 2, [604, 14], [24], home_stats=[14], away_stats=[24, 604]),
        synthetic(
            1005, "2015-09-12", 1, 2, swapped_home, swapped_away, home_stats=swapped_away, away_stats=swapped_home
        ),
        synthetic(1006, "2015-09-19", 1, 2, [0, 15], [0, 25]),
    ]
    p3 = [synthetic(3001, "2015-08-15", 3, 4, [501], [31], league=88)]  # 501 : deux équipes le même jour
    builder = build_multi(
        raw, p1, p3, profiles_p1=[profile(701, "1990-01-01")], profiles_p3=[profile(701, "1993-03-03")]
    )
    builder.queue.close()

    expected = RawChecker(raw, multi_config, ["P1", "P3"]).run(now=NOW)

    details = [*p1, *p3]
    same_match, players, days, teams, fixtures = {}, [], [], [], []
    for item in details:
        classified = col.classify_match(item["lineups"], item["players"])
        same_match |= {(item["fixture"]["id"], pid): kind for pid, kind in classified.collisions.items()}
        day = raw_check.fixture_day(item)
        for pid, team in classified.team.items():
            players.append(pid)
            days.append(day)
            teams.append(team)
            fixtures.append(item["fixture"]["id"])
    births = col.BirthIndex()
    births.add(701, "1990-01-01", 2015)
    births.add(701, "1993-03-03", 2015)

    assert same_match == {(c.fixture, c.player): c.subtype for c in expected.collisions_of(raw_check.SAME_MATCH)}
    assert {p for p, _ in col.same_day_collisions(players, days, teams, fixtures)} == {
        c.player for c in expected.collisions_of(raw_check.SAME_DAY)
    }
    assert births.collisions() == {c.player for c in expected.collisions_of(raw_check.BIRTH)}
