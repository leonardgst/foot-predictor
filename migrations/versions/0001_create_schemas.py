"""create base schemas: raw, staging, features

Revision ID: 0001_create_schemas
Revises:
Create Date: 2026-07-17
"""

from alembic import op

revision = "0001_create_schemas"
down_revision = None
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("CREATE SCHEMA IF NOT EXISTS raw")
    op.execute("CREATE SCHEMA IF NOT EXISTS staging")
    op.execute("CREATE SCHEMA IF NOT EXISTS features")


def downgrade() -> None:
    op.execute("DROP SCHEMA IF EXISTS features CASCADE")
    op.execute("DROP SCHEMA IF EXISTS staging CASCADE")
    op.execute("DROP SCHEMA IF EXISTS raw CASCADE")
