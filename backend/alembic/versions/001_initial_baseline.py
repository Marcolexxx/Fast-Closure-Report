"""Initial baseline — all tables from Base.metadata.

Revision ID: 001
Revises: 
Create Date: 2026-04-11 00:00:00.000000

This is a BASELINE migration that creates all tables from scratch.
If you have an existing database, run: alembic stamp 001
"""
from __future__ import annotations

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision: str = '001'
down_revision = None
branch_labels = None
depends_on = None


def upgrade() -> None:
    # NOTE: This migration is intentionally a no-op for existing databases.
    # The actual schema is managed by SQLAlchemy's create_all during startup.
    # Future incremental migrations should use proper op.create_table() / op.add_column() calls.
    # 
    # To baseline an existing DB:
    #   alembic stamp 001
    #
    # To let Alembic manage new changes going forward:
    #   alembic revision --autogenerate -m "description"
    pass


def downgrade() -> None:
    pass
