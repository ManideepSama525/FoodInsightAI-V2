"""Add personalized food profiles.

Revision ID: 0004_user_food_profiles
Revises: 0003_personal_food_records
"""
from alembic import op
import sqlalchemy as sa

revision = "0004_user_food_profiles"
down_revision = "0003_personal_food_records"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "user_food_profiles",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("user_id", sa.Integer(), nullable=False),
        sa.Column("allergies", sa.JSON(), nullable=False),
        sa.Column("intolerances", sa.JSON(), nullable=False),
        sa.Column("dietary_preferences", sa.JSON(), nullable=False),
        sa.Column("goals", sa.JSON(), nullable=False),
        sa.Column("disliked_foods", sa.JSON(), nullable=False),
        sa.Column("cuisine_interests", sa.JSON(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
        sa.UniqueConstraint("user_id", name="uq_user_food_profiles_user_id"),
    )
    op.create_index("ix_user_food_profiles_user_id", "user_food_profiles", ["user_id"])


def downgrade() -> None:
    op.drop_index("ix_user_food_profiles_user_id", table_name="user_food_profiles")
    op.drop_table("user_food_profiles")
