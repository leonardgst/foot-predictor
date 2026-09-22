"""Tests d'orchestration (`features/build_team_match_features.py`) : création
et mise à jour idempotente de `features.team_match_features`, en s'appuyant
sur les briques déjà testées unitairement (standing, forme, xG)."""
from __future__ import annotations

import datetime as dt

import pytest
from sqlalchemy import select

from foot_predictor.db.models import TeamMatchFeatures
from foot_predictor.features.build_team_match_features import build_all_team_match_features

pytestmark = pytest.mark.db


@pytest.fixture
def two_played_matches(make_competition, make_season, make_team, make_match, make_team_match):
    competition = make_competition()
    season = make_season(competition.id)
    team_a = make_team("A")
    team_b = make_team("B")

    match1 = make_match(
        competition_id=competition.id, season_id=season.id,
        match_date=dt.datetime(2024, 9, 1, tzinfo=dt.timezone.utc),
        home_team_id=team_a.id, away_team_id=team_b.id, home_goals=2, away_goals=0, status="played",
    )
    make_team_match(match_id=match1.id, team_id=team_a.id, is_home=True, goals_for=2, goals_against=0,
                     xg_for=1.8, xg_against=0.4)
    make_team_match(match_id=match1.id, team_id=team_b.id, is_home=False, goals_for=0, goals_against=2,
                     xg_for=0.4, xg_against=1.8)

    match2 = make_match(
        competition_id=competition.id, season_id=season.id,
        match_date=dt.datetime(2024, 9, 15, tzinfo=dt.timezone.utc),
        home_team_id=team_b.id, away_team_id=team_a.id, home_goals=1, away_goals=1, status="played",
    )
    make_team_match(match_id=match2.id, team_id=team_b.id, is_home=True, goals_for=1, goals_against=1)
    make_team_match(match_id=match2.id, team_id=team_a.id, is_home=False, goals_for=1, goals_against=1)

    return competition, season, team_a, team_b, match1, match2


def test_build_all_creates_one_row_per_team_match(db_session, two_played_matches):
    created, updated = build_all_team_match_features(db_session)

    assert created == 4  # 2 matchs x 2 team_match
    assert updated == 0

    rows = db_session.scalars(select(TeamMatchFeatures)).all()
    assert len(rows) == 4


def test_build_all_is_idempotent_on_second_run(db_session, two_played_matches):
    build_all_team_match_features(db_session)

    created_again, updated_again = build_all_team_match_features(db_session)

    assert created_again == 0
    assert updated_again == 4
    rows = db_session.scalars(select(TeamMatchFeatures)).all()
    assert len(rows) == 4  # pas de doublon


def test_second_match_standing_reflects_only_prior_result(db_session, two_played_matches):
    """Le match du 15/09 doit voir le classement calculé sur le seul match du
    01/09 (anti-fuite) : équipe A a gagné 2-0, donc 3 points avant ce match."""
    competition, season, team_a, team_b, match1, match2 = two_played_matches

    build_all_team_match_features(db_session)

    row_a_match2 = db_session.scalar(
        select(TeamMatchFeatures).where(
            TeamMatchFeatures.team_id == team_a.id,
            TeamMatchFeatures.match_id == match2.id,
        )
    )
    assert row_a_match2.standing_points == 3
    assert row_a_match2.standing_goal_diff == 2
