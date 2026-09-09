"""add user notes to transactions

Revision ID: 20260906_14
Revises: 20260906_13
"""

import sqlalchemy as sa
from alembic import op

revision = "20260906_14"
down_revision = "20260906_13"
branch_labels = None
depends_on = None


def upgrade():
    with op.batch_alter_table("transactions") as batch_op:
        batch_op.add_column(sa.Column("note", sa.String(length=500), nullable=False, server_default=""))
    with op.batch_alter_table("transactions") as batch_op:
        batch_op.alter_column("note", server_default=None)


def downgrade():
    with op.batch_alter_table("transactions") as batch_op:
        batch_op.drop_column("note")
