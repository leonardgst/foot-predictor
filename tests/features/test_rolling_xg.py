"""Tests du xG glissant (`features/rolling_xg.py`) : anti-fuite temporelle,
fenêtre de 5 matchs, exclusion des lignes sans xG renseigné, filtrage
domicile/extérieur.
"""
from __future__ import annotations

import datetime as dt

import pytest

from foot_predictor.features.rolling_xg import XG_WINDOW, compute_rolling_xg

pytestmark = pytest.mark.db

REF_DATE = dt.datetime(2025, 1, 1, tzinfo=dt.timezone.utc)


@pytest.fixture
def team_and_context(make_competition, make_season, make_team):
    competition = make_competition()
    season = make_season(competition.id)
    team = make_team("Focus FC")
    opponent = make_team("Opponent FC")
    return competition, season, team, opponent


def _add_match(make_match, make_team_match, *, competition, season, team, opponent, days_before, is_home,
                xg_for, xg_against, status="played"):
    match_date = REF_DATE - dt.timedelta(days=days_before)
    if is_home:
        match = make_match(
            competition_id=competition.id, season_id=season.id, match_date=match_date,
            home_team_id=team.id, away_team_id=opponent.id, home_goals=1, away_goals=0, status=status,
        )
    else:
        match = make_match(
            competition_id=competition.id, season_id=season.id, match_date=match_date,
            home_team_id=opponent.id, away_team_id=team.id, home_goals=0, away_goals=1, status=status,
        )
    make_team_match(
        match_id=match.id, team_id=team.id, is_home=is_home,
        goals_for=1, goals_against=0, xg_for=xg_for, xg_against=xg_against,
    )
    return match


def test_no_matches_returns_empty_snapshot(db_session, team_and_context):
    competition, season, team, opponent = team_and_context

    snapshot = compute_rolling_xg(db_session, team.id, True, REF_DATE)

    assert snapshot.xg_matches_count_last5 == 0
    assert snapshot.xg_for_last5 is None
    assert snapshot.xg_against_last5 is None


def test_excludes_matches_on_or_after_reference_date_anti_leakage(db_session, team_and_context, make_match, make_team_match):
    competition, season, team, opponent = team_and_context
    _add_match(make_match, make_team_match, competition=competition, season=season, team=team, opponent=opponent,
               days_before=1, is_home=True, xg_for=1.5, xg_against=0.5)
    future_match = make_match(
        competition_id=competition.id, season_id=season.id, match_date=REF_DATE,
        home_team_id=team.id, away_team_id=opponent.id, home_goals=3, away_goals=0, status="played",
    )
    make_team_match(match_id=future_match.id, team_id=team.id, is_home=True, goals_for=3, goals_against=0,
                     xg_for=9.9, xg_against=0.1)

    snapshot = compute_rolling_xg(db_session, team.id, True, REF_DATE)

    assert snapshot.xg_matches_count_last5 == 1
    assert snapshot.xg_for_last5 == 1.5


def test_excludes_rows_with_null_xg(db_session, team_and_context, make_match, make_team_match):
    """Un match dont xg_for/xg_against est encore NULL (Understat pas encore
    ingéré) doit être exclu de la fenêtre, pas compté comme 0."""
    competition, season, team, opponent = team_and_context
    _add_match(make_match, make_team_match, competition=competition, season=season, team=team, opponent=opponent,
               days_before=2, is_home=True, xg_for=2.0, xg_against=1.0)
    match_no_xg = make_match(
        competition_id=competition.id, season_id=season.id,
        match_date=REF_DATE - dt.timedelta(days=1),
        home_team_id=team.id, away_team_id=opponent.id, home_goals=1, away_goals=1, status="played",
    )
    make_team_match(match_id=match_no_xg.id, team_id=team.id, is_home=True, goals_for=1, goals_against=1,
                     xg_for=None, xg_against=None)

    snapshot = compute_rolling_xg(db_session, team.id, True, REF_DATE)

    assert snapshot.xg_matches_count_last5 == 1
    assert snapshot.xg_for_last5 == 2.0


def test_window_limited_to_xg_window_most_recent_matches(db_session, team_and_context, make_match, make_team_match):
    """7 matchs avec xG disponibles : seuls les XG_WINDOW (5) plus récents
    doivent compter."""
    competition, season, team, opponent = team_and_context
    for i in range(7):
        days_before = 7 - i
        xg_value = 0.5 if i < 2 else 2.0  # 2 plus anciens à 0.5, 5 plus récents à 2.0
        _add_match(make_match, make_team_match, competition=competition, season=season, team=team,
                   opponent=opponent, days_before=days_before, is_home=True, xg_for=xg_value, xg_against=1.0)

    snapshot = compute_rolling_xg(db_session, team.id, True, REF_DATE)

    assert snapshot.xg_matches_count_last5 == XG_WINDOW
    assert snapshot.xg_matches_count_last5 == 5
    assert snapshot.xg_for_last5 == 2.0


def test_early_season_fewer_matches_than_window(db_session, team_and_context, make_match, make_team_match):
    competition, season, team, opponent = team_and_context
    for days_before in (2, 1):
        _add_match(make_match, make_team_match, competition=competition, season=season, team=team,
                   opponent=opponent, days_before=days_before, is_home=True, xg_for=1.0, xg_against=0.5)

    snapshot = compute_rolling_xg(db_session, team.id, True, REF_DATE)

    assert snapshot.xg_matches_count_last5 == 2
    assert snapshot.xg_for_last5 == 1.0
    assert snapshot.xg_against_last5 == 0.5


def test_filters_by_home_away_context(db_session, team_and_context, make_match, make_team_match):
    competition, season, team, opponent = team_and_context
    _add_match(make_match, make_team_match, competition=competition, season=season, team=team, opponent=opponent,
               days_before=2, is_home=True, xg_for=3.0, xg_against=0.2)
    _add_match(make_match, make_team_match, competition=competition, season=season, team=team, opponent=opponent,
               days_before=1, is_home=False, xg_for=0.5, xg_against=1.5)

    home_snapshot = compute_rolling_xg(db_session, team.id, True, REF_DATE)
    away_snapshot = compute_rolling_xg(db_session, team.id, False, REF_DATE)

    assert home_snapshot.xg_matches_count_last5 == 1
    assert home_snapshot.xg_for_last5 == 3.0
    assert away_snapshot.xg_matches_count_last5 == 1
    assert away_snapshot.xg_for_last5 == 0.5
