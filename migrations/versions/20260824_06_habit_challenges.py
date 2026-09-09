"""add habit challenges

Revision ID: 20260824_06
Revises: 20260824_05
"""

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects.mysql import DATETIME

revision = "20260824_06"
down_revision = "20260824_05"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        "habit_challenges",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("user_id", sa.Integer(), sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=False),
        sa.Column("category_id", sa.Integer(), sa.ForeignKey("categories.id", ondelete="CASCADE"), nullable=False),
        sa.Column("baseline_count", sa.Integer(), nullable=False),
        sa.Column("target_count", sa.Integer(), nullable=False),
        sa.Column("average_amount", sa.BigInteger(), nullable=False),
        sa.Column("period_start", sa.Date()), sa.Column("period_end", sa.Date()),
        sa.Column("actual_count", sa.Integer()),
        sa.Column("saved_amount", sa.BigInteger(), nullable=False),
        sa.Column("status", sa.String(20), nullable=False),
        sa.Column("created_at", DATETIME(fsp=6), nullable=False),
        sa.CheckConstraint("baseline_count > 0", name="ck_habit_challenges_baseline"),
        sa.CheckConstraint("target_count > 0", name="ck_habit_challenges_target"),
        sa.CheckConstraint("average_amount > 0", name="ck_habit_challenges_average"),
        sa.CheckConstraint("status IN ('PROPOSED','ACTIVE','COMPLETED','FAILED','DECLINED')", name="ck_habit_challenges_status"),
        mysql_engine="InnoDB",
        mysql_charset="utf8mb4",
        mysql_collate="utf8mb4_0900_ai_ci",
    )
    op.create_index("ix_habit_challenges_user_status", "habit_challenges", ["user_id", "status"])


def downgrade():
    op.drop_index("ix_habit_challenges_user_status", table_name="habit_challenges")
    op.drop_table("habit_challenges")
