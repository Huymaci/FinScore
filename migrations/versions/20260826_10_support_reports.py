"""add persisted user support reports

Revision ID: 20260826_10
Revises: 20260826_09
"""

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects.mysql import DATETIME

revision = "20260826_10"
down_revision = "20260826_09"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        "support_reports",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("user_id", sa.Integer(), nullable=False),
        sa.Column("subject", sa.String(160), nullable=False),
        sa.Column("message", sa.Text(), nullable=False),
        sa.Column("status", sa.String(20), nullable=False),
        sa.Column("created_at", DATETIME(fsp=6), nullable=False),
        sa.Column("resolved_at", DATETIME(fsp=6), nullable=True),
        sa.CheckConstraint("status IN ('OPEN','RESOLVED')", name="ck_support_reports_status"),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "ix_support_reports_status_created",
        "support_reports",
        ["status", "created_at"],
        unique=False,
    )


def downgrade():
    op.drop_index("ix_support_reports_status_created", table_name="support_reports")
    op.drop_table("support_reports")
