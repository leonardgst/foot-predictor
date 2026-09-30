"""Migration 0007 (cotes de football-data) : montée, descente, contraintes."""

from __future__ import annotations

import pytest
from alembic import command
from sqlalchemy import inspect, text

from tests.db.test_migration_0004 import alembic_config

pytestmark = pytest.mark.db

BEFORE = "0006_dataset_version"


def test_downgrade_then_upgrade(_test_engine):
    try:
        command.downgrade(alembic_config(), BEFORE)
        assert "match_odds" not in inspect(_test_engine).get_table_names("staging")
        assert "dataset_version" in inspect(_test_engine).get_table_names("features")  # 0006 intacte
    finally:
        command.upgrade(alembic_config(), "head")
    assert "match_odds" in inspect(_test_engine).get_table_names("staging")


def test_constraints_are_declared(_test_engine):
    """Source, version et cotes > 1 contrôlées par la base, pas seulement par le chargeur ; une ligne par version."""
    checks = inspect(_test_engine).get_check_constraints("match_odds", schema="staging")
    names = {c["name"] for c in checks}
    assert {"ck_match_odds_source", "ck_match_odds_version", "ck_match_odds_decimal"} <= names
    uniques = inspect(_test_engine).get_unique_constraints("match_odds", schema="staging")
    assert [u["column_names"] for u in uniques] == [["match_id", "source", "version"]]
    with _test_engine.connect() as connection:
        assert connection.execute(text("SELECT count(*) FROM staging.match_odds")).scalar_one() == 0
