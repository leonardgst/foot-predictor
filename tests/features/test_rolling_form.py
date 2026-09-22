"""Tests de la forme récente / buts glissants (`features/rolling_form.py`) :
anti-fuite temporelle, taille de fenêtre, comportement en début de saison,
filtrage domicile/extérieur.
"""
from __future__ import annotations

import datetime as dt

import pytest

from foot_predictor.features.rolling_form import FORM_WINDOW, compute_rolling_form

pytestmark = pytest.mark.db

REF_DATE = dt.datetime(2025, 1, 1, tzinfo=dt.timezone.utc)


@pytest.fixture
def team_and_context(make_competition, make_season, make_team):
    competition = make_competition()
    season = make_season(competition.id)
    team = make_team("Focus FC")
    opponent = make_team("Opponent FC")
    return competition, season, team, opponent


def _add_match(make_match, make_team_match, *, competition, season, team, opponent, days_before, is_home, gf, ga, status="played"):
    match_date = REF_DATE - dt.timedelta(days=days_before)
    if is_home:
        match = make_match(
            competition_id=competition.id,
            season_id=season.id,
            match_date=match_date,
            home_team_id=team.id,
            away_team_id=opponent.id,
            home_goals=gf,
            away_goals=ga,
            status=status,
        )
    else:
        match = make_match(
            competition_id=competition.id,
            season_id=season.id,
            match_date=match_date,
            home_team_id=opponent.id,
            away_team_id=team.id,
            home_goals=ga,
            away_goals=gf,
            status=status,
        )
    make_team_match(match_id=match.id, team_id=team.id, is_home=is_home, goals_for=gf, goals_against=ga)
    return match


def test_no_matches_returns_empty_snapshot(db_session, team_and_context):
    competition, season, team, opponent = team_and_context

    snapshot = compute_rolling_form(db_session, team.id, True, REF_DATE)

    assert snapshot.form_matches_count == 0
    assert snapshot.form_points_last10 == 0
    assert snapshot.goals_for_last10 is None
    assert snapshot.goals_against_last10 is None


def test_excludes_matches_on_or_after_reference_date_anti_leakage(db_session, team_and_context, make_match, make_team_match):
    competition, season, team, opponent = team_and_context
    _add_match(make_match, make_team_match, competition=competition, season=season, team=team, opponent=opponent,
               days_before=1, is_home=True, gf=3, ga=0)
    # Match futur (>= before_date) : ne doit JAMAIS être compté.
    future_match = make_match(
        competition_id=competition.id,
        season_id=season.id,
        match_date=REF_DATE,
        home_team_id=team.id,
        away_team_id=opponent.id,
        home_goals=5,
        away_goals=0,
        status="played",
    )
    make_team_match(match_id=future_match.id, team_id=team.id, is_home=True, goals_for=5, goals_against=0)

    snapshot = compute_rolling_form(db_session, team.id, True, REF_DATE)

    assert snapshot.form_matches_count == 1
    assert snapshot.goals_for_last10 == 3.0


def test_excludes_non_played_matches(db_session, team_and_context, make_match, make_team_match):
    competition, season, team, opponent = team_and_context
    _add_match(make_match, make_team_match, competition=competition, season=season, team=team, opponent=opponent,
               days_before=1, is_home=True, gf=1, ga=1, status="scheduled")

    snapshot = compute_rolling_form(db_session, team.id, True, REF_DATE)

    assert snapshot.form_matches_count == 0


def test_window_limited_to_form_window_most_recent_matches(db_session, team_and_context, make_match, make_team_match):
    """12 matchs joués à domicile disponibles : seuls les FORM_WINDOW (10)
    plus récents doivent compter, pas les 2 plus anciens."""
    competition, season, team, opponent = team_and_context
    for i in range(12):
        # Les 2 plus anciens matchs (days_before=12, 11) marquent 0 but pour
        # équipe (défaite 0-5) ; les 10 plus récents marquent tous 1-0.
        days_before = 12 - i
        if i < 2:
            _add_match(make_match, make_team_match, competition=competition, season=season, team=team,
                       opponent=opponent, days_before=days_before, is_home=True, gf=0, ga=5)
        else:
            _add_match(make_match, make_team_match, competition=competition, season=season, team=team,
                       opponent=opponent, days_before=days_before, is_home=True, gf=1, ga=0)

    snapshot = compute_rolling_form(db_session, team.id, True, REF_DATE)

    assert snapshot.form_matches_count == FORM_WINDOW
    assert snapshot.form_matches_count == 10
    # Les 2 défaites 0-5 les plus anciennes sont hors fenêtre -> que des
    # victoires 1-0 comptées : 10 * 3 points, moyenne de buts 1.0 / 0.0.
    assert snapshot.form_points_last10 == 30
    assert snapshot.goals_for_last10 == 1.0
    assert snapshot.goals_against_last10 == 0.0


def test_early_season_fewer_matches_than_window(db_session, team_and_context, make_match, make_team_match):
    """Début de saison : moins de matchs disponibles que la fenêtre -> le
    calcul se fait quand même sur les matchs disponibles, sans erreur."""
    competition, season, team, opponent = team_and_context
    for days_before in (3, 2, 1):
        _add_match(make_match, make_team_match, competition=competition, season=season, team=team,
                   opponent=opponent, days_before=days_before, is_home=True, gf=2, ga=1)

    snapshot = compute_rolling_form(db_session, team.id, True, REF_DATE)

    assert snapshot.form_matches_count == 3
    assert snapshot.form_points_last10 == 9  # 3 victoires
    assert snapshot.goals_for_last10 == 2.0
    assert snapshot.goals_against_last10 == 1.0


def test_filters_by_home_away_context(db_session, team_and_context, make_match, make_team_match):
    competition, season, team, opponent = team_and_context
    _add_match(make_match, make_team_match, competition=competition, season=season, team=team, opponent=opponent,
               days_before=2, is_home=True, gf=4, ga=0)
    _add_match(make_match, make_team_match, competition=competition, season=season, team=team, opponent=opponent,
               days_before=1, is_home=False, gf=0, ga=2)

    home_snapshot = compute_rolling_form(db_session, team.id, True, REF_DATE)
    away_snapshot = compute_rolling_form(db_session, team.id, False, REF_DATE)

    assert home_snapshot.form_matches_count == 1
    assert home_snapshot.goals_for_last10 == 4.0
    assert away_snapshot.form_matches_count == 1
    assert away_snapshot.goals_for_last10 == 0.0
