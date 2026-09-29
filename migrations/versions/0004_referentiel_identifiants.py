"""référentiel par identifiants API : colonnes typées, entraîneurs, statistiques d'équipe, schéma ops

Revision ID: 0004_referentiel_identifiants
Revises: 0003_market_value_score
Create Date: 2026-09-29

Migration **additive** (partie 2, sous-étape 2.4 ; ADR-0008, ADR-0009,
ADR-0020) : aucune table ni colonne existante n'est supprimée ni renommée.
`features/` et `modeling/` continuent de lire les mêmes colonnes.

- Identifiants API typés et uniques (ADR-0008, règle 1) : `api_league_id`,
  `api_team_id`, `api_player_id`, `api_coach_id`, `api_fixture_id`. Les autres
  sources restent rattachées par les tables `*_source_mapping`.
- `staging.match` : coup d'envoi UTC, statut API, journée, score au temps
  réglementaire distinct du score final, tirs au but, exclusion (tapis vert,
  annulé, abandonné ; ADR-0009), origine « api » ou « hors_api ».
- Entraîneurs (`staging.coach`, `coach_source_mapping`, `team_match.coach_id`)
  et statistiques d'équipe par match (`staging.team_match_stats`, xG API).
- Compositions et statistiques joueurs : numéro, poste, grille.
- Compteurs par équipe et par match : titulaires inconnus (identifiant absent
  ou 0), entrées exclues pour collision (ADR-0020).
- Schéma `ops` et `ops.load_run` : une ligne par exécution de `load`.
- Index sur les clés étrangères utilisées par les jointures.
"""

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects.postgresql import ENUM as PGEnum
from sqlalchemy.dialects.postgresql import JSONB

revision = "0004_referentiel_identifiants"
down_revision = "0003_market_value_score"
branch_labels = None
depends_on = None

# Type déjà créé par la migration 0002 : réutilisé, jamais recréé ni supprimé ici.
position_bucket = PGEnum(
    "Goalkeeper", "Defender", "Midfielder", "Attacker", name="position_bucket", schema="staging", create_type=False
)

ORIGINS = "('api', 'hors_api')"
EXCLUSION_REASONS = "('tapis_vert', 'annule', 'abandonne')"

# (table, colonne) indexées : clés étrangères sans index jusqu'ici.
FK_INDEXES = [
    ("season", "competition_id"),
    ("match", "competition_id"),
    ("match", "season_id"),
    ("match", "home_team_id"),
    ("match", "away_team_id"),
    ("match", "match_date"),
    ("team_match", "team_id"),
    ("team_match", "coach_id"),
    ("lineup", "team_id"),
    ("lineup", "player_id"),
    ("player_match_stats", "team_id"),
    ("player_match_stats", "player_id"),
    ("player_injury", "player_id"),
    ("competition_source_mapping", "competition_id"),
    ("team_source_mapping", "team_id"),
    ("player_source_mapping", "player_id"),
    ("match_source_mapping", "match_id"),
]


def upgrade() -> None:
    # --- identifiants API typés -------------------------------------------------------
    op.add_column("competition", sa.Column("api_league_id", sa.Integer), schema="staging")
    op.add_column("competition", sa.Column("kind", sa.Text), schema="staging")
    op.create_unique_constraint("uq_competition_api_league_id", "competition", ["api_league_id"], schema="staging")
    op.create_check_constraint("ck_competition_kind", "competition", "kind IN ('league', 'cup')", schema="staging")

    op.add_column("season", sa.Column("year", sa.SmallInteger), schema="staging")
    op.create_unique_constraint("uq_season_competition_year", "season", ["competition_id", "year"], schema="staging")

    op.add_column("team", sa.Column("api_team_id", sa.Integer), schema="staging")
    op.add_column("team", sa.Column("origin", sa.Text), schema="staging")
    op.create_unique_constraint("uq_team_api_team_id", "team", ["api_team_id"], schema="staging")
    op.create_check_constraint("ck_team_origin", "team", f"origin IN {ORIGINS}", schema="staging")
    op.create_check_constraint(
        "ck_team_api_id_origin", "team", "origin IS DISTINCT FROM 'api' OR api_team_id IS NOT NULL", schema="staging"
    )

    op.add_column("player", sa.Column("api_player_id", sa.Integer), schema="staging")
    op.create_unique_constraint("uq_player_api_player_id", "player", ["api_player_id"], schema="staging")

    # --- matchs -------------------------------------------------------------------------
    for column in (
        sa.Column("api_fixture_id", sa.BigInteger),
        sa.Column("kickoff_utc", sa.DateTime(timezone=True)),
        sa.Column("status_short", sa.Text),
        sa.Column("round", sa.Text),
        # ADR-0009 : cible = buts au temps réglementaire (score.fulltime de l'API),
        # distincts du score final home_goals/away_goals (prolongations comprises).
        sa.Column("home_goals_90", sa.SmallInteger),
        sa.Column("away_goals_90", sa.SmallInteger),
        sa.Column("home_penalties", sa.SmallInteger),
        sa.Column("away_penalties", sa.SmallInteger),
        sa.Column("excluded", sa.Boolean, nullable=False, server_default=sa.false()),
        sa.Column("exclusion_reason", sa.Text),
        sa.Column("origin", sa.Text),
    ):
        op.add_column("match", column, schema="staging")
    op.create_unique_constraint("uq_match_api_fixture_id", "match", ["api_fixture_id"], schema="staging")
    op.create_check_constraint(
        "ck_match_exclusion_reason", "match", f"exclusion_reason IN {EXCLUSION_REASONS}", schema="staging"
    )
    op.create_check_constraint(
        "ck_match_excluded_has_reason", "match", "excluded = (exclusion_reason IS NOT NULL)", schema="staging"
    )
    op.create_check_constraint("ck_match_origin", "match", f"origin IN {ORIGINS}", schema="staging")
    op.create_check_constraint(
        "ck_match_api_id_origin",
        "match",
        "origin IS DISTINCT FROM 'api' OR api_fixture_id IS NOT NULL",
        schema="staging",
    )

    # --- entraîneurs --------------------------------------------------------------------
    op.create_table(
        "coach",
        sa.Column("id", sa.BigInteger, primary_key=True),
        sa.Column("api_coach_id", sa.Integer, nullable=False),
        sa.Column("name", sa.Text, nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.UniqueConstraint("api_coach_id", name="uq_coach_api_coach_id"),
        schema="staging",
    )
    op.create_table(
        "coach_source_mapping",
        sa.Column("id", sa.BigInteger, primary_key=True),
        sa.Column("coach_id", sa.BigInteger, sa.ForeignKey("staging.coach.id"), nullable=False),
        sa.Column("source_name", sa.Text, nullable=False),
        sa.Column("source_ref", sa.Text, nullable=False),
        sa.UniqueConstraint("source_name", "source_ref", name="uq_coach_source_mapping"),
        schema="staging",
    )
    op.create_index("ix_staging_coach_source_mapping_coach_id", "coach_source_mapping", ["coach_id"], schema="staging")

    # --- une équipe dans un match -------------------------------------------------------
    op.add_column(
        "team_match", sa.Column("coach_id", sa.BigInteger, sa.ForeignKey("staging.coach.id")), schema="staging"
    )
    op.add_column("team_match", sa.Column("formation", sa.Text), schema="staging")
    # Titulaires sans identifiant (null ou 0) : « inconnus », comptent 0 (ADR-0008, règle 1).
    op.add_column("team_match", sa.Column("unknown_starters", sa.SmallInteger), schema="staging")
    # Entrées (composition ou statistiques) exclues pour collision d'identifiant (ADR-0020).
    op.add_column("team_match", sa.Column("collision_excluded", sa.SmallInteger), schema="staging")

    op.create_table(
        "team_match_stats",
        sa.Column("id", sa.BigInteger, primary_key=True),
        sa.Column("team_match_id", sa.BigInteger, sa.ForeignKey("staging.team_match.id"), nullable=False),
        sa.Column("shots_on_goal", sa.SmallInteger),
        sa.Column("shots_off_goal", sa.SmallInteger),
        sa.Column("shots_total", sa.SmallInteger),
        sa.Column("shots_blocked", sa.SmallInteger),
        sa.Column("shots_inside_box", sa.SmallInteger),
        sa.Column("shots_outside_box", sa.SmallInteger),
        sa.Column("fouls", sa.SmallInteger),
        sa.Column("corners", sa.SmallInteger),
        sa.Column("offsides", sa.SmallInteger),
        sa.Column("possession_pct", sa.Numeric(5, 2)),
        sa.Column("yellow_cards", sa.SmallInteger),
        sa.Column("red_cards", sa.SmallInteger),
        sa.Column("goalkeeper_saves", sa.SmallInteger),
        sa.Column("passes_total", sa.SmallInteger),
        sa.Column("passes_accurate", sa.SmallInteger),
        sa.Column("passes_pct", sa.Numeric(5, 2)),
        sa.Column("expected_goals", sa.Numeric(5, 2)),  # absent avant 2022-23 dans le top 5 (ADR-0023)
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.UniqueConstraint("team_match_id", name="uq_team_match_stats"),
        schema="staging",
    )

    # --- compositions et statistiques joueurs -------------------------------------------
    op.add_column("lineup", sa.Column("shirt_number", sa.SmallInteger), schema="staging")
    op.add_column("lineup", sa.Column("grid", sa.Text), schema="staging")
    op.add_column("lineup", sa.Column("position_bucket", position_bucket), schema="staging")
    op.add_column("player_match_stats", sa.Column("shirt_number", sa.SmallInteger), schema="staging")
    op.add_column("player_match_stats", sa.Column("substitute", sa.Boolean), schema="staging")
    op.add_column("player_match_stats", sa.Column("captain", sa.Boolean), schema="staging")

    for table, column in FK_INDEXES:
        op.create_index(f"ix_staging_{table}_{column}", table, [column], schema="staging")

    # --- ops : exécutions du chargement ---------------------------------------------------
    op.execute("CREATE SCHEMA IF NOT EXISTS ops")
    op.create_table(
        "load_run",
        sa.Column("id", sa.BigInteger, primary_key=True),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("finished_at", sa.DateTime(timezone=True)),
        sa.Column("status", sa.Text, nullable=False),
        sa.Column("git_commit", sa.Text),
        sa.Column("raw_dir", sa.Text, nullable=False),
        sa.Column("external_raw_dir", sa.Text),
        sa.Column("manifests", JSONB, nullable=False),  # journal lu -> sha256
        sa.Column("counts", JSONB),  # décomptes par table et par motif
        sa.Column("fingerprints", JSONB),  # empreinte md5 de chaque table chargée
        sa.Column("duration_seconds", sa.Numeric(10, 1)),
        sa.CheckConstraint("status IN ('running', 'ok', 'failed')", name="ck_load_run_status"),
        schema="ops",
    )


def downgrade() -> None:
    op.drop_table("load_run", schema="ops")
    op.execute("DROP SCHEMA IF EXISTS ops")  # sans CASCADE : échoue si autre chose y a été créé

    for table, column in reversed(FK_INDEXES):
        op.drop_index(f"ix_staging_{table}_{column}", table_name=table, schema="staging")

    for column in ("captain", "substitute", "shirt_number"):
        op.drop_column("player_match_stats", column, schema="staging")
    for column in ("position_bucket", "grid", "shirt_number"):
        op.drop_column("lineup", column, schema="staging")

    op.drop_table("team_match_stats", schema="staging")
    for column in ("collision_excluded", "unknown_starters", "formation", "coach_id"):
        op.drop_column("team_match", column, schema="staging")
    op.drop_index("ix_staging_coach_source_mapping_coach_id", table_name="coach_source_mapping", schema="staging")
    op.drop_table("coach_source_mapping", schema="staging")
    op.drop_table("coach", schema="staging")

    for name in (
        "ck_match_api_id_origin",
        "ck_match_origin",
        "ck_match_excluded_has_reason",
        "ck_match_exclusion_reason",
    ):
        op.drop_constraint(name, "match", schema="staging", type_="check")
    op.drop_constraint("uq_match_api_fixture_id", "match", schema="staging", type_="unique")
    for column in (
        "origin",
        "exclusion_reason",
        "excluded",
        "away_penalties",
        "home_penalties",
        "away_goals_90",
        "home_goals_90",
        "round",
        "status_short",
        "kickoff_utc",
        "api_fixture_id",
    ):
        op.drop_column("match", column, schema="staging")

    op.drop_constraint("uq_player_api_player_id", "player", schema="staging", type_="unique")
    op.drop_column("player", "api_player_id", schema="staging")

    op.drop_constraint("ck_team_api_id_origin", "team", schema="staging", type_="check")
    op.drop_constraint("ck_team_origin", "team", schema="staging", type_="check")
    op.drop_constraint("uq_team_api_team_id", "team", schema="staging", type_="unique")
    op.drop_column("team", "origin", schema="staging")
    op.drop_column("team", "api_team_id", schema="staging")

    op.drop_constraint("uq_season_competition_year", "season", schema="staging", type_="unique")
    op.drop_column("season", "year", schema="staging")

    op.drop_constraint("ck_competition_kind", "competition", schema="staging", type_="check")
    op.drop_constraint("uq_competition_api_league_id", "competition", schema="staging", type_="unique")
    op.drop_column("competition", "kind", schema="staging")
    op.drop_column("competition", "api_league_id", schema="staging")
