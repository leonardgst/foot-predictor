"""tirs de football-data : statistiques d'équipe des sources externes

Revision ID: 0005_tirs_football_data
Revises: 0004_referentiel_identifiants
Create Date: 2026-09-29

Migration **additive** (partie 3, sous-étape 3.2 ; ADR-0029, révision partielle de
l'ADR-0027) : une table nouvelle, aucune table ni colonne existante modifiée.

`staging.team_match_stats_external` garde, par équipe et par match, les tirs et tirs
cadrés d'une source externe (aujourd'hui football-data : `HS`, `HST` pour l'équipe à
domicile, `AS`, `AST` pour l'équipe à l'extérieur). Les statistiques d'API-FOOTBALL
restent dans `staging.team_match_stats`, inchangée : les deux sources ne se mélangent
pas, et l'une sert à contrôler l'autre sur les matchs communs.
"""

import sqlalchemy as sa
from alembic import op

revision = "0005_tirs_football_data"
down_revision = "0004_referentiel_identifiants"
branch_labels = None
depends_on = None

SOURCES = "('football_data')"


def upgrade() -> None:
    op.create_table(
        "team_match_stats_external",
        sa.Column("id", sa.BigInteger, primary_key=True),
        sa.Column("source", sa.Text, nullable=False),
        sa.Column("team_match_id", sa.BigInteger, sa.ForeignKey("staging.team_match.id"), nullable=False),
        sa.Column("shots", sa.SmallInteger),  # vide si absent ou illisible dans la source, jamais 0 par défaut
        sa.Column("shots_on_target", sa.SmallInteger),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.UniqueConstraint("source", "team_match_id", name="uq_team_match_stats_external"),
        sa.CheckConstraint(f"source IN {SOURCES}", name="ck_team_match_stats_external_source"),
        schema="staging",
    )
    op.create_index(
        "ix_staging_team_match_stats_external_team_match_id",
        "team_match_stats_external",
        ["team_match_id"],
        schema="staging",
    )


def downgrade() -> None:
    op.drop_index(
        "ix_staging_team_match_stats_external_team_match_id", table_name="team_match_stats_external", schema="staging"
    )
    op.drop_table("team_match_stats_external", schema="staging")
