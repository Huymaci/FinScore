"""Store the private avatar filename for user profiles.

Revision ID: 20260826_09
Revises: 20260825_08
"""

import sqlalchemy as sa
from alembic import op

revision = "20260826_09"
down_revision = "20260825_08"
branch_labels = None
depends_on = None


def upgrade():
    with op.batch_alter_table("users") as batch_op:
        batch_op.add_column(sa.Column("avatar_filename", sa.String(255), nullable=True))


def downgrade():
    with op.batch_alter_table("users") as batch_op:
        batch_op.drop_column("avatar_filename")
