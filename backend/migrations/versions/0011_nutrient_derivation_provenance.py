"""Preserve USDA nutrient derivation provenance.

Revision ID: 0011_nutrient_derivation_provenance
Revises: 0010_recognition_alias_dish_target
"""

from alembic import op
import sqlalchemy as sa

revision = "0011_nutrient_derivation_provenance"
down_revision = "0010_recognition_alias_dish_target"
branch_labels = None
depends_on = None

TABLE = "food_nutrients"

COLUMNS = (
    ("derivation_code", sa.String(length=30)),
    ("derivation_description", sa.String(length=160)),
    ("derivation_source_description", sa.String(length=200)),
)


def upgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)

    if TABLE not in inspector.get_table_names():
        raise RuntimeError("food_nutrients table is missing")

    existing = {
        column["name"]
        for column in inspector.get_columns(TABLE)
    }

    for name, column_type in COLUMNS:
        if name not in existing:
            op.add_column(
                TABLE,
                sa.Column(name, column_type, nullable=True),
            )


def downgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)

    if TABLE not in inspector.get_table_names():
        return

    existing = {
        column["name"]
        for column in inspector.get_columns(TABLE)
    }

    for name, _ in reversed(COLUMNS):
        if name in existing:
            op.drop_column(TABLE, name)