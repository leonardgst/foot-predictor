"""Migration 0005 (tirs de football-data) : montée, descente, contraintes (base de test)."""

from __future__ import annotations

import datetime as dt

import pytest
from alembic import command
from sqlalchemy import inspect

from foot_predictor.db.models import Competition, Match, Season, Team, TeamMatch, TeamMatchStatsExternal
from tests.db.test_migration_0004 import alembic_config, fails

pytestmark = pytest.mark.db

BEFORE = "0004_referentiel_identifiants"


def test_downgrade_then_upgrade(_test_engine):
    try:
        command.downgrade(alembic_config(), BEFORE)
        tables = set(inspect(_test_engine).get_table_names("staging"))
        assert "team_match_stats_external" not in tables
        assert {"team_match_stats", "team_match", "match"} <= tables  # 0001 à 0004 intactes
    finally:
        command.upgrade(alembic_config(), "head")
    assert "team_match_stats_external" in inspect(_test_engine).get_table_names("staging")


@pytest.fixture
def team_match(db_session):
    competition = Competition(name="Ligue test", api_league_id=999_201, kind="league")
    home, away = Team(name="A", origin="hors_api"), Team(name="B", origin="hors_api")
    db_session.add_all([competition, home, away])
    db_session.flush()
    season = Season(
        competition_id=competition.id,
        label="2014-2015",
        year=2014,
        start_date=dt.date(2014, 7, 1),
        end_date=dt.date(2015, 6, 30),
    )
    db_session.add(season)
    db_session.flush()
    match = Match(
        competition_id=competition.id,
        season_id=season.id,
        match_date=dt.datetime(2014, 8, 16, tzinfo=dt.UTC),
        home_team_id=home.id,
        away_team_id=away.id,
        origin="hors_api",
    )
    db_session.add(match)
    db_session.flush()
    tm = TeamMatch(match_id=match.id, team_id=home.id, is_home=True)
    db_session.add(tm)
    db_session.flush()
    return tm


def test_one_row_per_source_and_team_match(db_session, team_match):
    row = lambda **v: TeamMatchStatsExternal(**({"source": "football_data", "team_match_id": team_match.id} | v))  # noqa: E731
    assert not fails(db_session, row(shots=12, shots_on_target=5))
    assert not fails(db_session, row(shots=None, shots_on_target=None))  # valeurs vides permises
    assert fails(db_session, row(), row())  # une seule ligne par (source, équipe-match)
    assert fails(db_session, row(source="understat"))  # source inconnue refusée
