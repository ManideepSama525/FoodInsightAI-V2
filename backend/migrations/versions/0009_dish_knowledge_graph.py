"""SQLite-safe, resumable Dish schema migration.

Revision ID: 0009_dish_knowledge_graph
Revises: 0008_ingredient_aliases
"""
from alembic import op
import sqlalchemy as sa

revision = "0009_dish_knowledge_graph"
down_revision = "0008_ingredient_aliases"
branch_labels = None
depends_on = None

FK_NAME = "fk_recognition_aliases_dish_id_dishes"
INDEX_NAME = "ix_recognition_aliases_dish_id"


def _table_names():
    return set(sa.inspect(op.get_bind()).get_table_names())


def upgrade() -> None:
    bind = op.get_bind()
    tables = _table_names()

    # These may already exist because the previous attempt completed these
    # operations before failing while adding the SQLite foreign key.
    if "dishes" not in tables:
        op.create_table(
            "dishes",
            sa.Column("id", sa.Integer(), primary_key=True),
            sa.Column("name", sa.String(240), nullable=False),
            sa.Column("normalized_name", sa.String(240), nullable=False),
            sa.Column("category", sa.String(120), nullable=True),
            sa.Column("source", sa.String(80), nullable=False, server_default="curated"),
            sa.Column("provenance", sa.JSON(), nullable=False, server_default=sa.text("'{}'")),
            sa.Column("is_active", sa.Boolean(), nullable=False, server_default=sa.true()),
            sa.UniqueConstraint("normalized_name", name="uq_dish_normalized_name"),
        )
    inspector = sa.inspect(bind)
    dish_indexes = {x["name"] for x in inspector.get_indexes("dishes")}
    if "ix_dishes_name" not in dish_indexes:
        op.create_index("ix_dishes_name", "dishes", ["name"])

    if "dish_recipes" not in _table_names():
        op.create_table(
            "dish_recipes",
            sa.Column("id", sa.Integer(), primary_key=True),
            sa.Column("dish_id", sa.Integer(), nullable=False),
            sa.Column("recipe_id", sa.Integer(), nullable=False),
            sa.Column("source", sa.String(80), nullable=False),
            sa.Column("provenance", sa.JSON(), nullable=False, server_default=sa.text("'{}'")),
            sa.Column("is_active", sa.Boolean(), nullable=False, server_default=sa.true()),
            sa.ForeignKeyConstraint(["dish_id"], ["dishes.id"], ondelete="CASCADE"),
            sa.ForeignKeyConstraint(["recipe_id"], ["recipes.id"], ondelete="CASCADE"),
            sa.UniqueConstraint("dish_id", "recipe_id", name="uq_dish_recipe_pair"),
        )
    inspector = sa.inspect(bind)
    assoc_indexes = {x["name"] for x in inspector.get_indexes("dish_recipes")}
    if "ix_dish_recipes_dish_id" not in assoc_indexes:
        op.create_index("ix_dish_recipes_dish_id", "dish_recipes", ["dish_id"])
    if "ix_dish_recipes_recipe_id" not in assoc_indexes:
        op.create_index("ix_dish_recipes_recipe_id", "dish_recipes", ["recipe_id"])

    # Add nullable dish_id if the earlier attempt did not add it.
    tables = _table_names()
    if "recognition_aliases" in tables:
        inspector = sa.inspect(bind)
        columns = {x["name"] for x in inspector.get_columns("recognition_aliases")}
        if "dish_id" not in columns:
            op.add_column("recognition_aliases", sa.Column("dish_id", sa.Integer(), nullable=True))

        # SQLite cannot ALTER TABLE ADD CONSTRAINT. Batch mode recreates the
        # table and safely adds the FK, including recovery after a partial run.
        inspector = sa.inspect(bind)
        fks = {x.get("name") for x in inspector.get_foreign_keys("recognition_aliases")}
        if FK_NAME not in fks:
            with op.batch_alter_table("recognition_aliases", recreate="always") as batch:
                batch.create_foreign_key(
                    FK_NAME, "dishes", ["dish_id"], ["id"], ondelete="CASCADE"
                )

        inspector = sa.inspect(bind)
        indexes = {x["name"] for x in inspector.get_indexes("recognition_aliases")}
        if INDEX_NAME not in indexes:
            op.create_index(INDEX_NAME, "recognition_aliases", ["dish_id"])


def downgrade() -> None:
    bind = op.get_bind()
    tables = _table_names()
    if "recognition_aliases" in tables:
        inspector = sa.inspect(bind)
        columns = {x["name"] for x in inspector.get_columns("recognition_aliases")}
        if "dish_id" in columns:
            indexes = {x["name"] for x in inspector.get_indexes("recognition_aliases")}
            if INDEX_NAME in indexes:
                op.drop_index(INDEX_NAME, table_name="recognition_aliases")
            fks = {x.get("name") for x in inspector.get_foreign_keys("recognition_aliases")}
            if FK_NAME in fks:
                with op.batch_alter_table("recognition_aliases", recreate="always") as batch:
                    batch.drop_constraint(FK_NAME, type_="foreignkey")
            with op.batch_alter_table("recognition_aliases", recreate="always") as batch:
                batch.drop_column("dish_id")

    if "dish_recipes" in _table_names():
        inspector = sa.inspect(bind)
        indexes = {x["name"] for x in inspector.get_indexes("dish_recipes")}
        for name in ("ix_dish_recipes_recipe_id", "ix_dish_recipes_dish_id"):
            if name in indexes:
                op.drop_index(name, table_name="dish_recipes")
        op.drop_table("dish_recipes")

    if "dishes" in _table_names():
        inspector = sa.inspect(bind)
        indexes = {x["name"] for x in inspector.get_indexes("dishes")}
        if "ix_dishes_name" in indexes:
            op.drop_index("ix_dishes_name", table_name="dishes")
        op.drop_table("dishes")
