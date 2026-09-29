"""Migration 0006 (traçabilité des jeux de données) : montée, descente, survie à un TRUNCATE de staging."""

from __future__ import annotations

import datetime as dt

import pytest
from alembic import command
from sqlalchemy import inspect, text

from foot_predictor.db.models import DatasetVersion
from tests.db.test_migration_0004 import alembic_config, fails

pytestmark = pytest.mark.db

BEFORE = "0005_tirs_football_data"


def test_downgrade_then_upgrade(_test_engine):
    try:
        command.downgrade(alembic_config(), BEFORE)
        assert "dataset_version" not in inspect(_test_engine).get_table_names("features")
        assert "team_match_stats_external" in inspect(_test_engine).get_table_names("staging")  # 0005 intacte
    finally:
        command.upgrade(alembic_config(), "head")
    assert "dataset_version" in inspect(_test_engine).get_table_names("features")


def version(**values) -> DatasetVersion:
    base = dict(
        version="ds-2026-09-29-00000000",
        created_at=dt.datetime(2026, 9, 29, tzinfo=dt.UTC),
        alembic_revision="0006_dataset_version",
        registry_sha256="a" * 64,
        manifest_sha256="b" * 64,
        parameters={},
        scope={},
        counts={},
        path="data/datasets/ds-2026-09-29-00000000",
    )
    return DatasetVersion(**(base | values))


def test_version_is_unique(db_session):
    assert not fails(db_session, version())
    assert fails(db_session, version(), version())


def test_trace_survives_a_staging_truncate(db_session):
    """`load` vide staging en cascade : la trace d'une version ne doit pas partir avec."""
    db_session.add(version())
    db_session.flush()
    db_session.execute(text("TRUNCATE staging.competition, staging.team CASCADE"))
    assert db_session.execute(text("SELECT count(*) FROM features.dataset_version")).scalar_one() == 1
