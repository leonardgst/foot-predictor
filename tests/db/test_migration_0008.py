"""Migration 0008 (ops.prediction, ops.model_registry) : montée, descente, survie à un TRUNCATE de staging."""

from __future__ import annotations

import pytest
from alembic import command
from sqlalchemy import inspect, text

from tests.db.test_migration_0004 import alembic_config

pytestmark = pytest.mark.db


def test_downgrade_then_upgrade(_test_engine):
    try:
        command.downgrade(alembic_config(), "0007_cotes_football_data")
        tables = inspect(_test_engine).get_table_names("ops")
        assert "prediction" not in tables and "model_registry" not in tables
        assert "match_odds" in inspect(_test_engine).get_table_names("staging")  # 0007 intacte
    finally:
        command.upgrade(alembic_config(), "head")
    assert {"prediction", "model_registry"} <= set(inspect(_test_engine).get_table_names("ops"))


def test_predictions_survive_a_staging_truncate(db_session):
    """`load` vide staging en cascade : l'historique des prédictions doit y survivre (aucune clé étrangère)."""
    db_session.execute(text(
        "INSERT INTO ops.prediction (match_id, match_day, model_version, horizon, mode, reference_date, status, reasons,"
        " variables_used, variables_not_present, data_version) VALUES (1, '2024-05-19', 'v', 'H1', 'replay',"
        " '2024-05-19', 'unavailable', '[]', '[]', '[]', 'x')"
    ))  # fmt: skip
    db_session.execute(text("TRUNCATE staging.competition, staging.team CASCADE"))
    assert db_session.execute(text("SELECT count(*) FROM ops.prediction")).scalar_one() == 1
