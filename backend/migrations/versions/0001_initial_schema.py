"""Create initial FoodInsightAI relational schema.

Revision ID: 0001_initial_schema
Revises:
Create Date: 2026-11-03
"""
from alembic import op

from backend.app.db.base import Base
from backend.app import models  # noqa: F401

revision = "0001_initial_schema"
down_revision = None
branch_labels = None
depends_on = None


def upgrade() -> None:
    bind = op.get_bind()
    Base.metadata.create_all(bind=bind)


def downgrade() -> None:
    bind = op.get_bind()
    Base.metadata.drop_all(bind=bind)
