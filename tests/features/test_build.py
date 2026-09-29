"""Commande `features build` de bout en bout sur la base de test : porte, instantané, traçabilité."""

from __future__ import annotations

import datetime as dt

import pytest
from sqlalchemy import text
from sqlalchemy.orm import Session

from foot_predictor.db.models import Competition, Match, Season, Team, TeamMatch
from foot_predictor.features.build import run_build
from foot_predictor.features.sources import load_dataset

pytestmark = pytest.mark.db


@pytest.fixture
def seeded(_test_engine):
    """Une saison synthétique de Premier League (4 équipes, 6 journées), écrite puis effacée."""
    with Session(_test_engine) as session:
        competition = Competition(name="Ligue test", api_league_id=39, kind="league", country="England")
        session.add(competition)
        session.flush()
        season = Season(
            competition_id=competition.id,
            label="2019-2020",
            year=2019,
            start_date=dt.date(2019, 7, 1),
            end_date=dt.date(2020, 6, 30),
        )
        teams = [Team(name=f"Équipe {i}", origin="hors_api") for i in range(4)]
        session.add_all([season, *teams])
        session.flush()
        pairs = [(0, 1), (2, 3), (1, 2), (3, 0), (0, 2), (1, 3)]
        for week, (h, a) in enumerate(pairs * 2):
            match = Match(
                competition_id=competition.id,
                season_id=season.id,
                match_date=dt.datetime(2019, 8, 3, 15, tzinfo=dt.UTC) + dt.timedelta(days=7 * (week // 2)),
                home_team_id=teams[h].id,
                away_team_id=teams[a].id,
                home_goals_90=week % 3,
                away_goals_90=(week + 1) % 2,
                status="played",
                origin="hors_api",
            )
            session.add(match)
            session.flush()
            session.add_all(
                [
                    TeamMatch(match_id=match.id, team_id=teams[h].id, is_home=True),
                    TeamMatch(match_id=match.id, team_id=teams[a].id, is_home=False),
                ]
            )
        session.commit()
    yield _test_engine
    with _test_engine.begin() as connection:
        connection.execute(text("TRUNCATE staging.competition, staging.team, features.dataset_version CASCADE"))


def test_build_writes_snapshot_and_trace_deterministically(seeded, tmp_path):
    first = run_build(output_root=tmp_path, record=True, engine=seeded, today=dt.date(2026, 9, 29))
    second = run_build(output_root=tmp_path, record=True, engine=seeded, today=dt.date(2026, 9, 29))
    assert first["version"] == second["version"]  # même contenu, même version
    assert first["rows"] == 24
    with seeded.connect() as connection:
        rows = connection.execute(text("SELECT version, alembic_revision FROM features.dataset_version")).all()
    assert [tuple(r) for r in rows] == [(first["version"], "0006_dataset_version")]
    frame, manifest = load_dataset(first["version"], tmp_path)
    assert len(frame) == 24 and manifest["counts"]["rows_by_phase"] == {"apprentissage": 24}
    assert manifest["parameters"]["seal_date"] == "2025-07-01"
