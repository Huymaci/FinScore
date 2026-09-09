"""Budget, alert and classification schema for UC-06 through UC-11.

Revision ID: 20260819_02
Revises: 20260819_01
"""
import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects.mysql import DATETIME

revision = "20260819_02"
down_revision = "20260819_01"
branch_labels = None
depends_on = None

TABLE_ARGS = {"mysql_engine": "InnoDB", "mysql_charset": "utf8mb4", "mysql_collate": "utf8mb4_0900_ai_ci"}
UTC = DATETIME(fsp=6)


def upgrade():
    op.create_table(
        "categorization_rules",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column("pattern", sa.String(255), nullable=False),
        sa.Column("category_id", sa.Integer(), nullable=False),
        # FR-15: rules are applied in priority order, so priority must be unique.
        sa.Column("priority", sa.Integer(), nullable=False),
        sa.Column("active", sa.Boolean(), nullable=False),
        sa.UniqueConstraint("priority", name="uq_rules_priority"),
        sa.ForeignKeyConstraint(["category_id"], ["categories.id"], ondelete="RESTRICT"),
        **TABLE_ARGS,
    )
    op.create_table(
        "budgets",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column("user_id", sa.Integer(), nullable=False),
        sa.Column("category_id", sa.Integer(), nullable=False),
        # Stored as the first day of the month.
        sa.Column("month", sa.Date(), nullable=False),
        sa.Column("amount", sa.BigInteger(), nullable=False),
        sa.CheckConstraint("amount >= 0", name="ck_budgets_amount"),
        sa.UniqueConstraint("user_id", "category_id", "month", name="uq_budget_user_category_month"),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["category_id"], ["categories.id"], ondelete="RESTRICT"),
        **TABLE_ARGS,
    )
    op.create_table(
        "alerts",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column("user_id", sa.Integer(), nullable=False),
        sa.Column("category_id", sa.Integer(), nullable=False),
        sa.Column("kind", sa.String(20), nullable=False),
        sa.Column("severity", sa.String(20), nullable=False),
        # FR-20: every alert explains why it fired and what to do about it.
        sa.Column("explanation", sa.String(500), nullable=False),
        sa.Column("suggested_action", sa.String(500), nullable=False),
        sa.Column("dedup_key", sa.String(100), nullable=False),
        sa.Column("status", sa.String(20), nullable=False),
        sa.Column("triggered_at", UTC, nullable=False),
        sa.CheckConstraint("severity IN ('WARNING','CRITICAL')", name="ck_alerts_severity"),
        sa.CheckConstraint("status IN ('UNREAD','READ','DISMISSED')", name="ck_alerts_status"),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["category_id"], ["categories.id"], ondelete="CASCADE"),
        **TABLE_ARGS,
    )
    # DR-06
    op.create_index("ix_alerts_user_triggered", "alerts", ["user_id", "triggered_at"])


def downgrade():
    op.drop_index("ix_alerts_user_triggered", table_name="alerts")
    op.drop_table("alerts")
    op.drop_table("budgets")
    op.drop_table("categorization_rules")
