"""Add curated food-recipe links and recognition aliases.

Revision ID: 0006_food_recipe_and_recognition_aliases
Revises: 0005_evidence_documents
"""
from alembic import op
import sqlalchemy as sa

revision = "0006_food_recipe_and_recognition_aliases"
down_revision = "0005_evidence_documents"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # 0001_initial_schema uses current Base.metadata.create_all(); on a fresh
    # install it may already have created these tables and indexes.
    bind = op.get_bind()
    inspector = sa.inspect(bind)

    if not inspector.has_table("food_recipes"):
        op.create_table(
            "food_recipes",
            sa.Column("id", sa.Integer(), primary_key=True),
            sa.Column("food_id", sa.Integer(), nullable=False),
            sa.Column("recipe_id", sa.Integer(), nullable=False),
            sa.Column("source", sa.String(length=80), nullable=False),
            sa.Column("provenance", sa.JSON(), nullable=False, server_default=sa.text("'{}'")),
            sa.Column("is_active", sa.Boolean(), nullable=False, server_default=sa.true()),
            sa.ForeignKeyConstraint(["food_id"], ["foods.id"], ondelete="CASCADE"),
            sa.ForeignKeyConstraint(["recipe_id"], ["recipes.id"], ondelete="CASCADE"),
            sa.UniqueConstraint("food_id", "recipe_id", name="uq_food_recipe_pair"),
        )
    inspector = sa.inspect(bind)
    food_recipe_indexes = {item["name"] for item in inspector.get_indexes("food_recipes")}
    if "ix_food_recipes_food_id" not in food_recipe_indexes:
        op.create_index("ix_food_recipes_food_id", "food_recipes", ["food_id"])
    if "ix_food_recipes_recipe_id" not in food_recipe_indexes:
        op.create_index("ix_food_recipes_recipe_id", "food_recipes", ["recipe_id"])

    if not inspector.has_table("recognition_aliases"):
        op.create_table(
            "recognition_aliases",
            sa.Column("id", sa.Integer(), primary_key=True),
            sa.Column("food_id", sa.Integer(), nullable=False),
            sa.Column("label", sa.String(length=240), nullable=False),
            sa.Column("normalized_label", sa.String(length=240), nullable=False),
            sa.Column("model_source", sa.String(length=40), nullable=False, server_default="any"),
            sa.Column("source", sa.String(length=80), nullable=False),
            sa.Column("provenance", sa.Text(), nullable=True),
            sa.Column("is_active", sa.Boolean(), nullable=False, server_default=sa.true()),
            sa.ForeignKeyConstraint(["food_id"], ["foods.id"], ondelete="CASCADE"),
            sa.UniqueConstraint(
                "model_source", "normalized_label",
                name="uq_recognition_alias_model_label",
            ),
        )
    inspector = sa.inspect(bind)
    alias_indexes = {item["name"] for item in inspector.get_indexes("recognition_aliases")}
    if "ix_recognition_aliases_food_id" not in alias_indexes:
        op.create_index("ix_recognition_aliases_food_id", "recognition_aliases", ["food_id"])
    if "ix_recognition_alias_normalized_label" not in alias_indexes:
        op.create_index(
            "ix_recognition_alias_normalized_label",
            "recognition_aliases",
            ["normalized_label"],
        )


def downgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    if inspector.has_table("recognition_aliases"):
        indexes = {item["name"] for item in inspector.get_indexes("recognition_aliases")}
        for name in ("ix_recognition_alias_normalized_label", "ix_recognition_aliases_food_id"):
            if name in indexes:
                op.drop_index(name, table_name="recognition_aliases")
        op.drop_table("recognition_aliases")
    inspector = sa.inspect(bind)
    if inspector.has_table("food_recipes"):
        indexes = {item["name"] for item in inspector.get_indexes("food_recipes")}
        for name in ("ix_food_recipes_recipe_id", "ix_food_recipes_food_id"):
            if name in indexes:
                op.drop_index(name, table_name="food_recipes")
        op.drop_table("food_recipes")
