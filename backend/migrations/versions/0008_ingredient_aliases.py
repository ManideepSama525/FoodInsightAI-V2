"""Add controlled ingredient aliases, separate from recognition aliases.

Revision ID: 0008_ingredient_aliases
Revises: 0007_recipe_import_provenance
"""
from alembic import op
import sqlalchemy as sa

revision = "0008_ingredient_aliases"
down_revision = "0007_recipe_import_provenance"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "ingredient_aliases",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("alias", sa.String(length=240), nullable=False),
        sa.Column("normalized_alias", sa.String(length=240), nullable=False),
        sa.Column("food_id", sa.Integer(), sa.ForeignKey("foods.id", ondelete="CASCADE"), nullable=True),
        sa.Column("candidate_food_id", sa.Integer(), sa.ForeignKey("foods.id", ondelete="SET NULL"), nullable=True),
        sa.Column("status", sa.String(length=30), nullable=False, server_default="review_required"),
        sa.Column("source", sa.String(length=80), nullable=False, server_default="manual_review"),
        sa.Column("provenance", sa.JSON(), nullable=False, server_default=sa.text("'{}'")),
        sa.UniqueConstraint("normalized_alias", name="uq_ingredient_alias_normalized"),
    )
    op.create_index("ix_ingredient_aliases_normalized_alias", "ingredient_aliases", ["normalized_alias"])
    op.create_index("ix_ingredient_aliases_food_id", "ingredient_aliases", ["food_id"])
    op.create_index("ix_ingredient_aliases_candidate_food_id", "ingredient_aliases", ["candidate_food_id"])
    op.create_index("ix_ingredient_aliases_status", "ingredient_aliases", ["status"])


def downgrade() -> None:
    # The table may contain reviewed mappings. Export it before any downgrade.
    op.drop_index("ix_ingredient_aliases_status", table_name="ingredient_aliases")
    op.drop_index("ix_ingredient_aliases_candidate_food_id", table_name="ingredient_aliases")
    op.drop_index("ix_ingredient_aliases_food_id", table_name="ingredient_aliases")
    op.drop_index("ix_ingredient_aliases_normalized_alias", table_name="ingredient_aliases")
    op.drop_table("ingredient_aliases")
