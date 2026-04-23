"""scan_messages table

Revision ID: 0002
Revises: 0001
Create Date: 2026-04-23

"""
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

revision = "0002"
down_revision = "0001"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "scan_messages",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "scan_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("scans.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("role", sa.String(length=16), nullable=False),
        sa.Column("content", sa.Text(), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
    )
    op.create_index(
        "idx_scan_messages_scan_id_created_at",
        "scan_messages",
        ["scan_id", "created_at"],
    )


def downgrade() -> None:
    op.drop_index("idx_scan_messages_scan_id_created_at", table_name="scan_messages")
    op.drop_table("scan_messages")
