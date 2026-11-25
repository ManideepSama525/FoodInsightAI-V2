"""Add versioned JWT revocation and response action audit records."""

from alembic import op
import sqlalchemy as sa

revision = "0012_security_session_revocation"
down_revision = "0011_nutrient_derivation_provenance"
branch_labels = None
depends_on = None


def upgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    tables = set(inspector.get_table_names())
    if "users" not in tables:
        raise RuntimeError("users table is missing; refusing session-revocation migration")

    user_columns = {column["name"] for column in inspector.get_columns("users")}
    if "token_version" not in user_columns:
        op.add_column(
            "users",
            sa.Column("token_version", sa.Integer(), nullable=False, server_default=sa.text("0")),
        )

    inspector = sa.inspect(bind)
    tables = set(inspector.get_table_names())
    if "security_response_actions" not in tables:
        op.create_table(
            "security_response_actions",
            sa.Column("id", sa.Integer(), primary_key=True),
            sa.Column("action_id", sa.String(length=36), nullable=False),
            sa.Column("incident_id", sa.String(length=20), nullable=False),
            sa.Column("action", sa.String(length=64), nullable=False),
            sa.Column("target_user_id", sa.Integer(), sa.ForeignKey("users.id"), nullable=False),
            sa.Column("reason", sa.Text(), nullable=False),
            sa.Column("performed_by", sa.String(length=64), nullable=False),
            sa.Column("previous_token_version", sa.Integer(), nullable=False),
            sa.Column("new_token_version", sa.Integer(), nullable=False),
            sa.Column("result", sa.String(length=20), nullable=False),
            sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
            sa.UniqueConstraint("action_id", name="uq_security_response_action_id"),
        )
        op.create_index(
            "ix_security_response_actions_target_user_id",
            "security_response_actions",
            ["target_user_id"],
        )


def downgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    if "security_response_actions" in inspector.get_table_names():
        indexes = {item["name"] for item in inspector.get_indexes("security_response_actions")}
        if "ix_security_response_actions_target_user_id" in indexes:
            op.drop_index("ix_security_response_actions_target_user_id", table_name="security_response_actions")
        op.drop_table("security_response_actions")

    inspector = sa.inspect(bind)
    if "users" in inspector.get_table_names():
        columns = {column["name"] for column in inspector.get_columns("users")}
        if "token_version" in columns:
            op.drop_column("users", "token_version")