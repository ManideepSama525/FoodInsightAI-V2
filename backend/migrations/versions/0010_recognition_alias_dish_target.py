"""Allow recognition aliases to target exactly one Food or Dish.

Revision ID: 0010_recognition_alias_dish_target
Revises: 0009_dish_knowledge_graph
"""
from alembic import op
import sqlalchemy as sa

revision = "0010_recognition_alias_dish_target"
down_revision = "0009_dish_knowledge_graph"
branch_labels = None
depends_on = None

TABLE = "recognition_aliases"
CHECK_NAME = "ck_recognition_alias_exactly_one_target"


def upgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    if TABLE not in inspector.get_table_names():
        raise RuntimeError("recognition_aliases table is missing")

    columns = {column["name"]: column for column in inspector.get_columns(TABLE)}
    if "food_id" not in columns or "dish_id" not in columns:
        raise RuntimeError("recognition_aliases must contain both food_id and dish_id")

    # Refuse to silently discard or reinterpret existing dual-target records.
    invalid = bind.execute(sa.text(
        "SELECT COUNT(*) FROM recognition_aliases "
        "WHERE (food_id IS NULL AND dish_id IS NULL) "
        "OR (food_id IS NOT NULL AND dish_id IS NOT NULL)"
    )).scalar_one()
    if invalid:
        raise RuntimeError(
            f"Found {invalid} recognition aliases with zero or two targets; "
            "review them before applying this migration."
        )

    checks = {item.get("name") for item in inspector.get_check_constraints(TABLE)}
    food_nullable = columns["food_id"]["nullable"]
    if food_nullable and CHECK_NAME in checks:
        return

    with op.batch_alter_table(TABLE, recreate="always") as batch:
        if not food_nullable:
            batch.alter_column(
                "food_id",
                existing_type=columns["food_id"]["type"],
                existing_nullable=False,
                nullable=True,
            )
        if CHECK_NAME not in checks:
            batch.create_check_constraint(
                CHECK_NAME,
                "(food_id IS NOT NULL AND dish_id IS NULL) OR "
                "(food_id IS NULL AND dish_id IS NOT NULL)",
            )


def downgrade() -> None:
    bind = op.get_bind()
    dish_only = bind.execute(sa.text(
        "SELECT COUNT(*) FROM recognition_aliases "
        "WHERE food_id IS NULL AND dish_id IS NOT NULL"
    )).scalar_one()
    if dish_only:
        raise RuntimeError(
            f"Cannot downgrade: {dish_only} Dish-targeted aliases have no food_id. "
            "Migrate or remove them explicitly first."
        )

    inspector = sa.inspect(bind)
    columns = {column["name"]: column for column in inspector.get_columns(TABLE)}
    checks = {item.get("name") for item in inspector.get_check_constraints(TABLE)}
    with op.batch_alter_table(TABLE, recreate="always") as batch:
        if CHECK_NAME in checks:
            batch.drop_constraint(CHECK_NAME, type_="check")
        if columns["food_id"]["nullable"]:
            batch.alter_column(
                "food_id",
                existing_type=columns["food_id"]["type"],
                existing_nullable=True,
                nullable=False,
            )
