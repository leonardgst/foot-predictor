"""cotes plus/moins 2,5 de football-data : référence de marché du protocole

Revision ID: 0007_cotes_football_data
Revises: 0006_dataset_version
Create Date: 2026-09-30

Migration **additive** (partie 4, sous-étape 4.1 ; ADR-0036, chargeur prévu par l'ADR-0027) :
une table nouvelle, aucune table ni colonne existante modifiée.

`staging.match_odds` garde, par match, par source et par version (« avant_cloture » ou
« cloture »), les cotes décimales plus et moins 2,5 buts, la colonne du CSV retenue et le
nombre de cotes agrégées (vide quand la source ne le publie pas). Le marché est une
**référence**, jamais une variable (décision M18) ; la table est reconstruite par `load`
comme le reste de `staging`.
"""

import sqlalchemy as sa
from alembic import op

revision = "0007_cotes_football_data"
down_revision = "0006_dataset_version"
branch_labels = None
depends_on = None

SOURCES = "('football_data')"
VERSIONS = "('avant_cloture', 'cloture')"


def upgrade() -> None:
    op.create_table(
        "match_odds",
        sa.Column("id", sa.BigInteger, primary_key=True),
        sa.Column("match_id", sa.BigInteger, sa.ForeignKey("staging.match.id"), nullable=False),
        sa.Column("source", sa.Text, nullable=False),
        sa.Column("version", sa.Text, nullable=False),
        sa.Column("odds_over_2_5", sa.Numeric(7, 3), nullable=False),
        sa.Column("odds_under_2_5", sa.Numeric(7, 3), nullable=False),
        sa.Column("odds_column", sa.Text, nullable=False),  # préfixe de la colonne du CSV : Avg, BbAv, B365…
        sa.Column("n_odds", sa.SmallInteger),  # vide si la source ne publie pas le nombre de cotes agrégées
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.UniqueConstraint("match_id", "source", "version", name="uq_match_odds"),
        sa.CheckConstraint(f"source IN {SOURCES}", name="ck_match_odds_source"),
        sa.CheckConstraint(f"version IN {VERSIONS}", name="ck_match_odds_version"),
        sa.CheckConstraint("odds_over_2_5 > 1 AND odds_under_2_5 > 1", name="ck_match_odds_decimal"),
        schema="staging",
    )
    op.create_index("ix_staging_match_odds_match_id", "match_odds", ["match_id"], schema="staging")


def downgrade() -> None:
    op.drop_index("ix_staging_match_odds_match_id", table_name="match_odds", schema="staging")
    op.drop_table("match_odds", schema="staging")
