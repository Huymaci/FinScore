"""track import transaction removal for one-month history retention

Revision ID: 20260905_12
Revises: 20260901_11
"""

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects.mysql import DATETIME

revision = "20260905_12"
down_revision = "20260901_11"
branch_labels = None
depends_on = None


def upgrade():
    column_type = DATETIME(fsp=6) if op.get_bind().dialect.name == "mysql" else sa.DateTime()
    with op.batch_alter_table("import_batches") as batch_op:
        batch_op.add_column(sa.Column("reverted_at", column_type, nullable=True))
    # The exact removal time of legacy rows was not recorded. Starting their
    # retention clock at migration time avoids deleting that history early.
    op.execute(sa.text(
        "UPDATE import_batches SET reverted_at = CURRENT_TIMESTAMP "
        "WHERE status = 'REVERTED' AND reverted_at IS NULL"
    ))


def downgrade():
    with op.batch_alter_table("import_batches") as batch_op:
        batch_op.drop_column("reverted_at")
