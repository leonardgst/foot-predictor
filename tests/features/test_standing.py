"""Tests du classement (`features/standing.py`) : snapshot anti-fuite,
tri par points puis différence de buts.
"""
from __future__ import annotations

import datetime as dt

import pytest

from foot_predictor.features.standing import compute_standings_before_date

pytestmark = pytest.mark.db

REF_DATE = dt.datetime(2025, 1, 1, tzinfo=dt.timezone.utc)


@pytest.fixture
def league(make_competition, make_season, make_team):
    competition = make_competition()
    season = make_season(competition.id)
    teams = {name: make_team(name) for name in ("A", "B", "C")}
    return competition, season, teams


def _play(make_match, make_team_match, *, competition, season, home, away, home_goals, away_goals, days_before):
    match = make_match(
        competition_id=competition.id,
        season_id=season.id,
        match_date=REF_DATE - dt.timedelta(days=days_before),
        home_team_id=home.id,
        away_team_id=away.id,
        home_goals=home_goals,
        away_goals=away_goals,
        status="played",
    )
    make_team_match(match_id=match.id, team_id=home.id, is_home=True, goals_for=home_goals, goals_against=away_goals)
    make_team_match(match_id=match.id, team_id=away.id, is_home=False, goals_for=away_goals, goals_against=home_goals)
    return match


def test_excludes_matches_on_or_after_reference_date_anti_leakage(db_session, league, make_match, make_team_match):
    competition, season, teams = league
    _play(make_match, make_team_match, competition=competition, season=season,
          home=teams["A"], away=teams["B"], home_goals=2, away_goals=0, days_before=1)
    # Match futur (à la date de référence exacte) : ne doit pas compter.
    future = make_match(
        competition_id=competition.id, season_id=season.id, match_date=REF_DATE,
        home_team_id=teams["B"].id, away_team_id=teams["A"].id, home_goals=5, away_goals=0, status="played",
    )
    make_team_match(match_id=future.id, team_id=teams["B"].id, is_home=True, goals_for=5, goals_against=0)
    make_team_match(match_id=future.id, team_id=teams["A"].id, is_home=False, goals_for=0, goals_against=5)

    standings = compute_standings_before_date(db_session, competition.id, season.id, REF_DATE)

    assert standings[teams["A"].id].points == 3
    assert standings[teams["B"].id].points == 0


def test_excludes_scheduled_matches(db_session, league, make_match, make_team_match):
    competition, season, teams = league
    scheduled = make_match(
        competition_id=competition.id, season_id=season.id,
        match_date=REF_DATE - dt.timedelta(days=1),
        home_team_id=teams["A"].id, away_team_id=teams["B"].id,
        home_goals=None, away_goals=None, status="scheduled",
    )

    standings = compute_standings_before_date(db_session, competition.id, season.id, REF_DATE)

    assert teams["A"].id not in standings
    assert teams["B"].id not in standings


def test_ranking_sorted_by_points_then_goal_diff(db_session, league, make_match, make_team_match):
    competition, season, teams = league
    # A bat B 3-0 (A: 3pts, +3 gd) puis A bat C 1-0 (A: 6pts, +4 gd)
    _play(make_match, make_team_match, competition=competition, season=season,
          home=teams["A"], away=teams["B"], home_goals=3, away_goals=0, days_before=3)
    _play(make_match, make_team_match, competition=competition, season=season,
          home=teams["A"], away=teams["C"], home_goals=1, away_goals=0, days_before=2)
    # B bat C 4-0 (B: 3pts, +4 gd ; C: 0pt, -4 gd)
    _play(make_match, make_team_match, competition=competition, season=season,
          home=teams["B"], away=teams["C"], home_goals=4, away_goals=0, days_before=1)

    standings = compute_standings_before_date(db_session, competition.id, season.id, REF_DATE)

    assert standings[teams["A"].id].points == 6
    assert standings[teams["A"].id].position == 1
    # B et C ont tous deux 3 points d'écart de classement mais B a un
    # meilleur goal_diff (+1 : -0+3+4=... recalcul : B a 0pt vs A (défaite),
    # 3pts vs C (victoire 4-0) -> 3pts, gd = (0-3)+(4-0) = 1
    assert standings[teams["B"].id].points == 3
    assert standings[teams["B"].id].goal_diff == 1
    assert standings[teams["C"].id].points == 0
    assert standings[teams["B"].id].position == 2
    assert standings[teams["C"].id].position == 3


def test_no_matches_returns_empty_dict(db_session, league):
    competition, season, teams = league

    standings = compute_standings_before_date(db_session, competition.id, season.id, REF_DATE)

    assert standings == {}
