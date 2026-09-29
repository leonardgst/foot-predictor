"""traçabilité des jeux de données : features.dataset_version

Revision ID: 0006_dataset_version
Revises: 0005_tirs_football_data
Create Date: 2026-09-29

Migration **additive** (partie 3, sous-étape 3.3 ; ADR-0030) : une table nouvelle dans le
schéma `features`, aucune table ni colonne existante modifiée.

Le jeu de données lui-même est un instantané Parquet (`data/datasets/<version>/`, ignoré par
Git) ; la base n'en garde que la **traçabilité** : une ligne par version construite.

La table n'a **aucune clé étrangère vers `staging`** : `load` vide `staging` et, par cascade,
les tables `features` qui en dépendent ; la trace d'une version doit survivre à un
rechargement. `load_run_id` pointe vers `ops.load_run` (jamais vidé par `load`).
"""

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects.postgresql import JSONB

revision = "0006_dataset_version"
down_revision = "0005_tirs_football_data"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "dataset_version",
        sa.Column("id", sa.BigInteger, primary_key=True),
        sa.Column("version", sa.Text, nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("git_commit", sa.Text),
        sa.Column("alembic_revision", sa.Text, nullable=False),
        sa.Column("load_run_id", sa.BigInteger, sa.ForeignKey("ops.load_run.id")),
        sa.Column("registry_sha256", sa.Text, nullable=False),
        sa.Column("manifest_sha256", sa.Text, nullable=False),
        sa.Column("parameters", JSONB, nullable=False),
        sa.Column("scope", JSONB, nullable=False),
        sa.Column("counts", JSONB, nullable=False),
        sa.Column("path", sa.Text, nullable=False),
        sa.UniqueConstraint("version", name="uq_dataset_version_version"),
        schema="features",
    )


def downgrade() -> None:
    op.drop_table("dataset_version", schema="features")
