"""Create persistent evidence documents for hybrid retrieval.

Revision ID: 0005_evidence_documents
Revises: 0004_user_food_profiles
"""

from alembic import op
import sqlalchemy as sa


revision = "0005_evidence_documents"
down_revision = "0004_user_food_profiles"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "evidence_documents",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("source_type", sa.String(length=40), nullable=False),
        sa.Column("source_id", sa.String(length=160), nullable=False),
        sa.Column("title", sa.String(length=500), nullable=False),
        sa.Column("content", sa.Text(), nullable=False),
        sa.Column(
            "provenance",
            sa.JSON(),
            nullable=False,
            server_default=sa.text("'{}'"),
        ),
        sa.Column("content_hash", sa.String(length=64), nullable=False),
        sa.Column(
            "status",
            sa.String(length=20),
            nullable=False,
            server_default="pending",
        ),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
        sa.UniqueConstraint(
            "source_type",
            "source_id",
            name="uq_evidence_source",
        ),
    )

    op.create_index(
        "ix_evidence_documents_source_type",
        "evidence_documents",
        ["source_type"],
    )
    op.create_index(
        "ix_evidence_documents_content_hash",
        "evidence_documents",
        ["content_hash"],
    )
    op.create_index(
        "ix_evidence_documents_status",
        "evidence_documents",
        ["status"],
    )


def downgrade() -> None:
    op.drop_index(
        "ix_evidence_documents_status",
        table_name="evidence_documents",
    )
    op.drop_index(
        "ix_evidence_documents_content_hash",
        table_name="evidence_documents",
    )
    op.drop_index(
        "ix_evidence_documents_source_type",
        table_name="evidence_documents",
    )
    op.drop_table("evidence_documents")