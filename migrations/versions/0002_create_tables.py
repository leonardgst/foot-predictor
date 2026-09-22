"""create staging, raw and features tables

Revision ID: 0002_create_tables
Revises: 0001_create_schemas
Create Date: 2026-07-18

À placer dans : migrations/versions/0002_create_tables.py

IMPORTANT : remplacer la valeur de `down_revision` ci-dessous par le revision id
réel de la migration 0001 (visible en tête de son fichier), s'il diffère de
"0001_create_schemas".
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import JSONB, ENUM as PGEnum

# revision identifiers, used by Alembic.
revision = "0002_create_tables"
down_revision = "0001_create_schemas"
branch_labels = None
depends_on = None


match_status_enum = PGEnum(
    "scheduled", "played", "postponed", "cancelled",
    name="match_status",
    schema="staging",
)


def upgrade() -> None:
    # Note : le type enum "match_status" est créé automatiquement par Postgres/SQLAlchemy
    # au moment du create_table("match") ci-dessous (colonne "status"), pas besoin de le
    # créer explicitement en amont.

    # =========================================================
    # staging — référentiels de base (pas de dépendance externe)
    # =========================================================

    op.create_table(
        "competition",
        sa.Column("id", sa.BigInteger, primary_key=True),
        sa.Column("name", sa.Text, nullable=False),
        sa.Column("country", sa.Text),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        schema="staging",
    )

    op.create_table(
        "season",
        sa.Column("id", sa.BigInteger, primary_key=True),
        sa.Column("competition_id", sa.BigInteger, sa.ForeignKey("staging.competition.id"), nullable=False),
        sa.Column("label", sa.Text, nullable=False),
        sa.Column("start_date", sa.Date, nullable=False),
        sa.Column("end_date", sa.Date, nullable=False),
        schema="staging",
    )

    op.create_table(
        "team",
        sa.Column("id", sa.BigInteger, primary_key=True),
        sa.Column("name", sa.Text, nullable=False),
        sa.Column("country", sa.Text),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        schema="staging",
    )

    op.create_table(
        "player",
        sa.Column("id", sa.BigInteger, primary_key=True),
        sa.Column("full_name", sa.Text, nullable=False),
        sa.Column("birth_date", sa.Date),
        sa.Column("nationality", sa.Text),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        schema="staging",
    )

    # -- tables de mapping (dépendent des référentiels ci-dessus)

    op.create_table(
        "competition_source_mapping",
        sa.Column("id", sa.BigInteger, primary_key=True),
        sa.Column("competition_id", sa.BigInteger, sa.ForeignKey("staging.competition.id"), nullable=False),
        sa.Column("source_name", sa.Text, nullable=False),
        sa.Column("source_ref", sa.Text, nullable=False),
        sa.UniqueConstraint("source_name", "source_ref", name="uq_competition_source_mapping"),
        schema="staging",
    )

    op.create_table(
        "team_source_mapping",
        sa.Column("id", sa.BigInteger, primary_key=True),
        sa.Column("team_id", sa.BigInteger, sa.ForeignKey("staging.team.id"), nullable=False),
        sa.Column("source_name", sa.Text, nullable=False),
        sa.Column("source_ref", sa.Text, nullable=False),
        sa.UniqueConstraint("source_name", "source_ref", name="uq_team_source_mapping"),
        schema="staging",
    )

    op.create_table(
        "player_source_mapping",
        sa.Column("id", sa.BigInteger, primary_key=True),
        sa.Column("player_id", sa.BigInteger, sa.ForeignKey("staging.player.id"), nullable=False),
        sa.Column("source_name", sa.Text, nullable=False),
        sa.Column("source_ref", sa.Text, nullable=False),
        sa.UniqueConstraint("source_name", "source_ref", name="uq_player_source_mapping"),
        schema="staging",
    )

    # -- match et dépendants

    op.create_table(
        "match",
        sa.Column("id", sa.BigInteger, primary_key=True),
        sa.Column("competition_id", sa.BigInteger, sa.ForeignKey("staging.competition.id"), nullable=False),
        sa.Column("season_id", sa.BigInteger, sa.ForeignKey("staging.season.id"), nullable=False),
        sa.Column("match_date", sa.DateTime(timezone=True), nullable=False),
        sa.Column("home_team_id", sa.BigInteger, sa.ForeignKey("staging.team.id"), nullable=False),
        sa.Column("away_team_id", sa.BigInteger, sa.ForeignKey("staging.team.id"), nullable=False),
        sa.Column("home_goals", sa.SmallInteger),
        sa.Column("away_goals", sa.SmallInteger),
        sa.Column("status", match_status_enum, nullable=False, server_default="scheduled"),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        schema="staging",
    )

    op.create_table(
        "match_source_mapping",
        sa.Column("id", sa.BigInteger, primary_key=True),
        sa.Column("match_id", sa.BigInteger, sa.ForeignKey("staging.match.id"), nullable=False),
        sa.Column("source_name", sa.Text, nullable=False),
        sa.Column("source_ref", sa.Text, nullable=False),
        sa.UniqueConstraint("source_name", "source_ref", name="uq_match_source_mapping"),
        schema="staging",
    )

    op.create_table(
        "team_match",
        sa.Column("id", sa.BigInteger, primary_key=True),
        sa.Column("match_id", sa.BigInteger, sa.ForeignKey("staging.match.id"), nullable=False),
        sa.Column("team_id", sa.BigInteger, sa.ForeignKey("staging.team.id"), nullable=False),
        sa.Column("is_home", sa.Boolean, nullable=False),
        sa.Column("goals_for", sa.SmallInteger),
        sa.Column("goals_against", sa.SmallInteger),
        sa.Column("xg_for", sa.Numeric(4, 2)),
        sa.Column("xg_against", sa.Numeric(4, 2)),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.UniqueConstraint("match_id", "team_id", name="uq_team_match"),
        schema="staging",
    )

    op.create_table(
        "lineup",
        sa.Column("id", sa.BigInteger, primary_key=True),
        sa.Column("match_id", sa.BigInteger, sa.ForeignKey("staging.match.id"), nullable=False),
        sa.Column("team_id", sa.BigInteger, sa.ForeignKey("staging.team.id"), nullable=False),
        sa.Column("player_id", sa.BigInteger, sa.ForeignKey("staging.player.id"), nullable=False),
        sa.Column("started", sa.Boolean, nullable=False),
        sa.Column("position", sa.Text),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.UniqueConstraint("match_id", "team_id", "player_id", name="uq_lineup"),
        schema="staging",
    )

    op.create_table(
        "player_valuation",
        sa.Column("id", sa.BigInteger, primary_key=True),
        sa.Column("player_id", sa.BigInteger, sa.ForeignKey("staging.player.id"), nullable=False),
        sa.Column("value_date", sa.Date, nullable=False),
        sa.Column("value_eur", sa.BigInteger, nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.UniqueConstraint("player_id", "value_date", name="uq_player_valuation"),
        schema="staging",
    )

    # =========================================================
    # raw — copie brute par source (jsonb, pas de FK inter-tables raw)
    # =========================================================

    op.create_table(
        "source_ingestion_log",
        sa.Column("id", sa.BigInteger, primary_key=True),
        sa.Column("source_name", sa.Text, nullable=False),
        sa.Column("ingested_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.Column("payload_ref", sa.Text),
        sa.Column("status", sa.Text, nullable=False),
        schema="raw",
    )

    for table_name in (
        "football_data_match",
        "transfermarkt_lineup",
        "transfermarkt_valuation",
        "understat_match_stats",
    ):
        op.create_table(
            table_name,
            sa.Column("id", sa.BigInteger, primary_key=True),
            sa.Column("ingestion_id", sa.BigInteger, sa.ForeignKey("raw.source_ingestion_log.id"), nullable=False),
            sa.Column("raw_payload", JSONB, nullable=False),
            sa.Column("ingested_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
            schema="raw",
        )

    # =========================================================
    # features — variables calculées (dépend de staging)
    # =========================================================

    op.create_table(
        "team_match_features",
        sa.Column("id", sa.BigInteger, primary_key=True),
        sa.Column("team_match_id", sa.BigInteger, sa.ForeignKey("staging.team_match.id"), nullable=False),
        sa.Column("match_id", sa.BigInteger, sa.ForeignKey("staging.match.id"), nullable=False),
        sa.Column("team_id", sa.BigInteger, sa.ForeignKey("staging.team.id"), nullable=False),
        sa.Column("computed_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.Column("form_points_last10", sa.SmallInteger),
        sa.Column("form_matches_count", sa.SmallInteger),
        sa.Column("goals_for_last10", sa.Numeric(4, 2)),
        sa.Column("goals_against_last10", sa.Numeric(4, 2)),
        sa.Column("xg_for_last5", sa.Numeric(4, 2)),
        sa.Column("xg_against_last5", sa.Numeric(4, 2)),
        sa.Column("xg_matches_count_last5", sa.SmallInteger),
        sa.Column("standing_position", sa.SmallInteger),
        sa.Column("standing_points", sa.SmallInteger),
        sa.Column("standing_goal_diff", sa.SmallInteger),
        sa.Column("squad_valuation_eur", sa.BigInteger),
        sa.Column("squad_avg_age", sa.Numeric(4, 2)),
        sa.Column("squad_stability_score_season", sa.Numeric(5, 4)),
        sa.UniqueConstraint("team_match_id", name="uq_team_match_features"),
        schema="features",
    )


def downgrade() -> None:
    # Ordre inverse strict pour respecter les FK
    op.drop_table("team_match_features", schema="features")

    for table_name in (
        "understat_match_stats",
        "transfermarkt_valuation",
        "transfermarkt_lineup",
        "football_data_match",
    ):
        op.drop_table(table_name, schema="raw")
    op.drop_table("source_ingestion_log", schema="raw")

    op.drop_table("player_valuation", schema="staging")
    op.drop_table("lineup", schema="staging")
    op.drop_table("team_match", schema="staging")
    op.drop_table("match_source_mapping", schema="staging")
    op.drop_table("match", schema="staging")
    op.drop_table("player_source_mapping", schema="staging")
    op.drop_table("team_source_mapping", schema="staging")
    op.drop_table("competition_source_mapping", schema="staging")
    op.drop_table("player", schema="staging")
    op.drop_table("team", schema="staging")
    op.drop_table("season", schema="staging")
    op.drop_table("competition", schema="staging")

    match_status_enum.drop(op.get_bind(), checkfirst=True)
