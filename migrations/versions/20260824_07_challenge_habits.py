"""identify challenges by recurring behavior

Revision ID: 20260824_07
Revises: 20260824_06
"""

import sqlalchemy as sa
from alembic import op

revision = "20260824_07"
down_revision = "20260824_06"
branch_labels = None
depends_on = None


def upgrade():
    # server_default exists only to backfill rows written before this revision;
    # it is dropped immediately so the column matches the model definition and
    # `alembic revision --autogenerate` stays clean.
    op.add_column("habit_challenges", sa.Column("habit_key", sa.String(160), nullable=False, server_default=""))
    op.add_column("habit_challenges", sa.Column("habit_name", sa.String(160), nullable=False, server_default=""))
    op.execute("DELETE FROM habit_challenges WHERE status = 'PROPOSED'")
    # SQLite cannot execute ``ALTER TABLE ... ALTER COLUMN``. Alembic's batch
    # mode recreates the table there, while still issuing normal ALTERs on
    # databases (such as MySQL) that support them.
    with op.batch_alter_table("habit_challenges") as batch_op:
        batch_op.alter_column("habit_key", existing_type=sa.String(160), nullable=False, server_default=None)
        batch_op.alter_column("habit_name", existing_type=sa.String(160), nullable=False, server_default=None)


def downgrade():
    with op.batch_alter_table("habit_challenges") as batch_op:
        batch_op.drop_column("habit_name")
        batch_op.drop_column("habit_key")
