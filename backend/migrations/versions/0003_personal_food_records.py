"""Add recipe ownership and personal food diary.

Revision ID: 0003_personal_food_records
Revises: 0002_users
"""
from alembic import op
import sqlalchemy as sa

revision = "0003_personal_food_records"
down_revision = "0002_users"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # SQLite requires batch mode to add a foreign key to an existing table.
    with op.batch_alter_table("recipes", recreate="auto") as batch_op:
        batch_op.add_column(sa.Column("user_id", sa.Integer(), nullable=True))
        batch_op.create_foreign_key(
            "fk_recipes_user_id_users",
            "users",
            ["user_id"],
            ["id"],
            ondelete="CASCADE",
        )
        batch_op.create_index("ix_recipes_user_id", ["user_id"])

    op.create_table(
        "diary_entries",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("user_id", sa.Integer(), nullable=False),
        sa.Column("food_id", sa.Integer(), nullable=False),
        sa.Column("quantity_g", sa.Numeric(12, 3), nullable=False),
        sa.Column("meal_type", sa.String(20), nullable=False),
        sa.Column("consumed_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("notes", sa.Text(), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
        sa.ForeignKeyConstraint(
            ["user_id"], ["users.id"],
            ondelete="CASCADE",
            name="fk_diary_entries_user_id_users",
        ),
        sa.ForeignKeyConstraint(
            ["food_id"], ["foods.id"],
            name="fk_diary_entries_food_id_foods",
        ),
    )
    op.create_index("ix_diary_entries_user_id", "diary_entries", ["user_id"])
    op.create_index("ix_diary_entries_food_id", "diary_entries", ["food_id"])
    op.create_index(
        "ix_diary_entries_user_consumed",
        "diary_entries",
        ["user_id", "consumed_at"],
    )


def downgrade() -> None:
    op.drop_index("ix_diary_entries_user_consumed", table_name="diary_entries")
    op.drop_index("ix_diary_entries_food_id", table_name="diary_entries")
    op.drop_index("ix_diary_entries_user_id", table_name="diary_entries")
    op.drop_table("diary_entries")

    with op.batch_alter_table("recipes", recreate="auto") as batch_op:
        batch_op.drop_index("ix_recipes_user_id")
        batch_op.drop_constraint(
            "fk_recipes_user_id_users",
            type_="foreignkey",
        )
        batch_op.drop_column("user_id")