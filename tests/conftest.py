"""Fixtures pytest communes.

Force APP_ENV=test avant tout import de foot_predictor.config, pour que les
tests utilisant une vraie base (marqueur `db`) pointent toujours vers la base
Postgres de test (docker-compose, port 5433) et jamais vers dev/prod, quelle
que soit la variable d'environnement du shell appelant.
"""
from __future__ import annotations

import datetime as dt
import os

os.environ["APP_ENV"] = "test"

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import Session

from foot_predictor.config import get_settings
from foot_predictor.db.models import Competition, Match, Season, Team, TeamMatch, TeamMatchFeatures


@pytest.fixture(scope="session")
def _test_engine():
    """Engine connecté à la base de test. Si elle est injoignable (sandbox
    sans Docker, CI sans Postgres), les tests marqués `db` sont skip plutôt
    que de planter -- cf. README pour lancer `docker compose up -d` en local."""
    settings = get_settings()
    engine = create_engine(settings.database_url)
    try:
        with engine.connect():
            pass
    except Exception as exc:
        pytest.skip(
            f"Base de test Postgres injoignable ({settings.postgres_host}:{settings.postgres_port}) : {exc}"
        )
    yield engine
    engine.dispose()


@pytest.fixture
def db_session(_test_engine):
    """Session SQLAlchemy connectée à la base de test, dans une transaction
    ouverte au début du test et annulée (rollback) à la fin : aucune donnée
    créée par un test ne persiste en base, quel que soit son résultat."""
    connection = _test_engine.connect()
    transaction = connection.begin()
    session = Session(bind=connection)

    yield session

    session.close()
    transaction.rollback()
    connection.close()


@pytest.fixture
def make_competition(db_session):
    def _make(name: str = "Premier League", country: str | None = "England") -> Competition:
        competition = Competition(name=name, country=country)
        db_session.add(competition)
        db_session.flush()
        return competition

    return _make


@pytest.fixture
def make_season(db_session):
    def _make(competition_id: int, label: str = "2024-2025") -> Season:
        start_year = int(label.split("-")[0])
        season = Season(
            competition_id=competition_id,
            label=label,
            start_date=dt.date(start_year, 7, 1),
            end_date=dt.date(start_year + 1, 6, 30),
        )
        db_session.add(season)
        db_session.flush()
        return season

    return _make


@pytest.fixture
def make_team(db_session):
    def _make(name: str) -> Team:
        team = Team(name=name)
        db_session.add(team)
        db_session.flush()
        return team

    return _make


@pytest.fixture
def make_match(db_session):
    def _make(
        *,
        competition_id: int,
        season_id: int,
        match_date: dt.datetime,
        home_team_id: int,
        away_team_id: int,
        home_goals: int | None = None,
        away_goals: int | None = None,
        status: str = "played",
    ) -> Match:
        match = Match(
            competition_id=competition_id,
            season_id=season_id,
            match_date=match_date,
            home_team_id=home_team_id,
            away_team_id=away_team_id,
            home_goals=home_goals,
            away_goals=away_goals,
            status=status,
        )
        db_session.add(match)
        db_session.flush()
        return match

    return _make


@pytest.fixture
def make_team_match(db_session):
    def _make(
        *,
        match_id: int,
        team_id: int,
        is_home: bool,
        goals_for: int | None = None,
        goals_against: int | None = None,
        xg_for: float | None = None,
        xg_against: float | None = None,
    ) -> TeamMatch:
        team_match = TeamMatch(
            match_id=match_id,
            team_id=team_id,
            is_home=is_home,
            goals_for=goals_for,
            goals_against=goals_against,
            xg_for=xg_for,
            xg_against=xg_against,
        )
        db_session.add(team_match)
        db_session.flush()
        return team_match

    return _make


@pytest.fixture
def make_team_match_features(db_session):
    def _make(
        *,
        team_match_id: int,
        match_id: int,
        team_id: int,
        **feature_values,
    ) -> TeamMatchFeatures:
        features = TeamMatchFeatures(
            team_match_id=team_match_id,
            match_id=match_id,
            team_id=team_id,
            **feature_values,
        )
        db_session.add(features)
        db_session.flush()
        return features

    return _make
