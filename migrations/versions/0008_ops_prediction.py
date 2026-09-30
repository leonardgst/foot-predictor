"""traçabilité des prédictions : ops.prediction et ops.model_registry

Revision ID: 0008_ops_prediction
Revises: 0007_cotes_football_data
Create Date: 2026-09-30

Migration **additive** (partie 5, sous-étape 5.4 ; ADR-0040, décision 7 ; rapport F.2, couches 3
et 4) : deux tables nouvelles dans le schéma `ops`, aucune table ni colonne existante modifiée.

- `ops.model_registry` : une ligne par modèle entraîné (version, carte d'identité, chemin) ; au
  plus **un** modèle actif (index unique partiel).
- `ops.prediction` : une ligne par prédiction (match, version du modèle, horizon, mode, date de
  référence, date de création) : λ, loi du total, intervalle et couverture annoncée, variables
  utilisées et non présentes, statut, raisons, fraîcheur des données. Les modes `replay` et `live`
  sont séparés : l'évaluation prospective de 2026-27 ne lit que `live`.

`ops.prediction` n'a **aucune clé étrangère vers `staging`** : `load` vide `staging` en cascade, et
l'historique des prédictions (surtout le live, preuve prospective) doit y survivre. Les
identifiants de match sont stables d'un chargement à l'autre (ADR-0008) ; l'identifiant de match
d'API-FOOTBALL et les équipes sont recopiés pour rester lisibles quoi qu'il arrive.
"""

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects.postgresql import JSONB

revision = "0008_ops_prediction"
down_revision = "0007_cotes_football_data"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "model_registry",
        sa.Column("version", sa.Text, primary_key=True),
        sa.Column("horizon", sa.Text, nullable=False),
        sa.Column("card", JSONB, nullable=False),
        sa.Column("path", sa.Text, nullable=False),
        sa.Column("active", sa.Boolean, nullable=False, server_default=sa.false()),
        sa.Column("registered_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.CheckConstraint("horizon IN ('H1', 'H2')", name="ck_model_registry_horizon"),
        schema="ops",
    )
    op.create_index(
        "uq_model_registry_one_active",
        "model_registry",
        ["active"],
        unique=True,
        schema="ops",
        postgresql_where=sa.text("active"),
    )
    op.create_table(
        "prediction",
        sa.Column("id", sa.BigInteger, primary_key=True),
        sa.Column("match_id", sa.BigInteger, nullable=False),
        sa.Column("api_fixture_id", sa.BigInteger),
        sa.Column("competition_id", sa.BigInteger),
        sa.Column("home_team_id", sa.BigInteger),
        sa.Column("away_team_id", sa.BigInteger),
        sa.Column("kickoff_utc", sa.DateTime(timezone=True)),
        sa.Column("match_day", sa.Date, nullable=False),
        sa.Column("model_version", sa.Text, nullable=False),
        sa.Column("horizon", sa.Text, nullable=False),
        sa.Column("mode", sa.Text, nullable=False),
        sa.Column("reference_date", sa.Date, nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("status", sa.Text, nullable=False),
        sa.Column("reasons", JSONB, nullable=False),
        sa.Column("lambda_home", sa.Float),
        sa.Column("lambda_away", sa.Float),
        sa.Column("expected_total", sa.Float),
        sa.Column("total_distribution", JSONB),
        sa.Column("p_over_2_5", sa.Float),
        sa.Column("interval_low", sa.SmallInteger),
        sa.Column("interval_high", sa.SmallInteger),
        sa.Column("announced_coverage", sa.Float),
        sa.Column("variables_used", JSONB, nullable=False),
        sa.Column("variables_not_present", JSONB, nullable=False),
        sa.Column("data_version", sa.Text, nullable=False),
        sa.Column("data_complete_until", sa.Date),
        sa.CheckConstraint("horizon IN ('H1', 'H2')", name="ck_prediction_horizon"),
        sa.CheckConstraint("mode IN ('replay', 'live')", name="ck_prediction_mode"),
        sa.CheckConstraint(
            "status IN ('available', 'unavailable', 'out_of_scope', 'excluded', 'h2_unavailable')",
            name="ck_prediction_status",
        ),
        sa.CheckConstraint(
            "(status = 'available') = (lambda_home IS NOT NULL AND total_distribution IS NOT NULL)",
            name="ck_prediction_values_iff_available",
        ),
        schema="ops",
    )
    op.create_index(
        "ix_ops_prediction_lookup", "prediction", ["match_id", "model_version", "horizon", "mode"], schema="ops"
    )
    op.create_index("ix_ops_prediction_mode_day", "prediction", ["mode", "match_day"], schema="ops")


def downgrade() -> None:
    op.drop_index("ix_ops_prediction_mode_day", table_name="prediction", schema="ops")
    op.drop_index("ix_ops_prediction_lookup", table_name="prediction", schema="ops")
    op.drop_table("prediction", schema="ops")
    op.drop_index("uq_model_registry_one_active", table_name="model_registry", schema="ops")
    op.drop_table("model_registry", schema="ops")
