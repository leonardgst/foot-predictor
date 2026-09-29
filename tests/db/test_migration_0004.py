"""Migration 0004 : montée, descente, contraintes, accord avec les modèles (base de test)."""

from __future__ import annotations

import datetime as dt
from pathlib import Path

import pytest
from alembic import command
from alembic.autogenerate import compare_metadata
from alembic.config import Config
from alembic.migration import MigrationContext
from sqlalchemy import inspect
from sqlalchemy.exc import IntegrityError

from foot_predictor.db.models import Base, Competition, Match, Season, Team

pytestmark = pytest.mark.db

REPO = Path(__file__).resolve().parents[2]
BEFORE, AFTER = "0003_market_value_score", "0004_referentiel_identifiants"


def alembic_config() -> Config:
    config = Config(str(REPO / "alembic.ini"))
    config.set_main_option("script_location", str(REPO / "migrations"))
    return config


def columns(engine, table: str, schema: str = "staging") -> set[str]:
    return {column["name"] for column in inspect(engine).get_columns(table, schema=schema)}


def test_models_match_migrations(_test_engine):
    """Les modèles SQLAlchemy décrivent exactement le schéma produit par les migrations."""
    with _test_engine.connect() as connection:
        context = MigrationContext.configure(connection, opts={"include_schemas": True})
        assert compare_metadata(context, Base.metadata) == []


def test_downgrade_then_upgrade(_test_engine):
    try:
        command.downgrade(alembic_config(), BEFORE)
        inspector = inspect(_test_engine)
        assert "ops" not in inspector.get_schema_names()
        assert not {"coach", "coach_source_mapping", "team_match_stats"} & set(inspector.get_table_names("staging"))
        assert "api_team_id" not in columns(_test_engine, "team")
        assert "home_goals_90" not in columns(_test_engine, "match")
        assert {"home_goals", "away_goals", "status"} <= columns(_test_engine, "match")  # 0002 intacte
    finally:
        command.upgrade(alembic_config(), "head")
    inspector = inspect(_test_engine)
    assert "load_run" in inspector.get_table_names("ops")
    assert {"api_fixture_id", "home_goals_90", "excluded", "exclusion_reason", "origin"} <= columns(
        _test_engine, "match"
    )
    assert {"coach_id", "unknown_starters", "collision_excluded"} <= columns(_test_engine, "team_match")


@pytest.fixture
def season(db_session):
    competition = Competition(name="Ligue test", api_league_id=999_001, kind="league")
    db_session.add(competition)
    db_session.flush()
    season = Season(
        competition_id=competition.id,
        label="2024-2025",
        year=2024,
        start_date=dt.date(2024, 7, 1),
        end_date=dt.date(2025, 6, 30),
    )
    db_session.add(season)
    db_session.flush()
    return season


def fails(db_session, *objects) -> bool:
    """Vrai si l'insertion viole une contrainte ; la session reste utilisable."""
    savepoint = db_session.begin_nested()
    try:
        db_session.add_all(objects)
        db_session.flush()
    except IntegrityError:
        savepoint.rollback()
        return True
    savepoint.rollback()
    return False


def test_api_identifiers_are_unique(db_session):
    assert fails(db_session, Team(name="A", api_team_id=42, origin="api"), Team(name="B", api_team_id=42, origin="api"))
    assert not fails(
        db_session, Team(name="A", api_team_id=42, origin="api"), Team(name="B", api_team_id=43, origin="api")
    )


def test_team_origin_rules(db_session):
    assert fails(db_session, Team(name="A", origin="autre"))
    assert fails(db_session, Team(name="A", origin="api"))  # « api » exige un identifiant API
    assert not fails(db_session, Team(name="A", origin="hors_api"))


def test_match_exclusion_and_origin_rules(db_session, season):
    home, away = Team(name="A", api_team_id=1, origin="api"), Team(name="B", api_team_id=2, origin="api")
    db_session.add_all([home, away])
    db_session.flush()

    def match(**values) -> Match:
        base = dict(
            competition_id=season.competition_id,
            season_id=season.id,
            match_date=dt.datetime(2024, 8, 17, tzinfo=dt.UTC),
            home_team_id=home.id,
            away_team_id=away.id,
            origin="api",
            api_fixture_id=10,
        )
        return Match(**(base | values))

    assert not fails(db_session, match())
    assert not fails(db_session, match(excluded=True, exclusion_reason="tapis_vert"))
    assert fails(db_session, match(excluded=True))  # exclu sans motif
    assert fails(db_session, match(exclusion_reason="annule"))  # motif sans exclusion
    assert fails(db_session, match(excluded=True, exclusion_reason="pluie"))
    assert fails(db_session, match(api_fixture_id=None))  # « api » sans identifiant
    assert not fails(db_session, match(api_fixture_id=None, origin="hors_api"))
    assert fails(db_session, match(), match())  # identifiant de match unique
