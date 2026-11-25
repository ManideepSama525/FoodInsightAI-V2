"""Add source provenance and honest ingredient quantity/mapping states.

Revision ID: 0007_recipe_import_provenance
Revises: 0006_food_recipe_and_recognition_aliases
"""
from alembic import op
import sqlalchemy as sa

revision = "0007_recipe_import_provenance"
down_revision = "0006_food_recipe_and_recognition_aliases"
branch_labels = None
depends_on = None


def upgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    recipe_columns = {c["name"] for c in inspector.get_columns("recipes")}
    for name, column in [
        ("source", sa.Column("source", sa.String(80), nullable=True)),
        ("external_id", sa.Column("external_id", sa.String(160), nullable=True)),
        ("source_url", sa.Column("source_url", sa.String(1000), nullable=True)),
        ("source_license", sa.Column("source_license", sa.String(160), nullable=True)),
        ("source_attribution", sa.Column("source_attribution", sa.String(500), nullable=True)),
        ("source_metadata", sa.Column("source_metadata", sa.JSON(), nullable=False, server_default=sa.text("'{}'"))),
    ]:
        if name not in recipe_columns:
            op.add_column("recipes", column)

    inspector = sa.inspect(bind)
    indexes = {i["name"] for i in inspector.get_indexes("recipes")}
    if "ix_recipes_source" not in indexes:
        op.create_index("ix_recipes_source", "recipes", ["source"])
    uniques = {u.get("name") for u in inspector.get_unique_constraints("recipes")}
    if "uq_recipe_source_external_id" not in uniques:
        with op.batch_alter_table("recipes") as batch:
            batch.create_unique_constraint(
                "uq_recipe_source_external_id", ["source", "external_id"]
            )

    ingredient_columns = {c["name"]: c for c in inspector.get_columns("recipe_ingredients")}
    for name, column in [
        ("raw_ingredient_text", sa.Column("raw_ingredient_text", sa.Text(), nullable=True)),
        ("mapping_status", sa.Column("mapping_status", sa.String(30), nullable=False, server_default="unmapped")),
        ("quantity_status", sa.Column("quantity_status", sa.String(30), nullable=False, server_default="unknown")),
    ]:
        if name not in ingredient_columns:
            op.add_column("recipe_ingredients", column)

    # A source ingredient may legitimately have no numeric amount or unit.
    if ingredient_columns.get("quantity", {}).get("nullable") is False:
        with op.batch_alter_table("recipe_ingredients") as batch:
            batch.alter_column("quantity", existing_type=sa.Numeric(12, 3), nullable=True)
    if ingredient_columns.get("unit", {}).get("nullable") is False:
        with op.batch_alter_table("recipe_ingredients") as batch:
            batch.alter_column("unit", existing_type=sa.String(30), nullable=True)


def downgrade() -> None:
    # Do not silently discard imported provenance or ingredient source text.
    # Downgrade is intentionally blocked unless an operator has backed up/exported data.
    raise RuntimeError(
        "Migration 0007 is data-bearing; restore a pre-migration backup instead of downgrading."
    )
