"""widen import_batches.preview_json for realistic statement sizes

Revision ID: 20260901_11
Revises: 20260826_10

MySQL TEXT holds 65,535 bytes. A single 183-row statement with Vietnamese
descriptions, a 64-character dedup_key hex per row and a category-reason
sentence overruns it, and every import of the MB-template files failed with
(1406, "Data too long for column 'preview_json'"). SQLite imposes no such
limit, which is why the unit suite stayed green while MySQL rejected the write.
"""
import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects.mysql import LONGTEXT

revision = "20260901_11"
down_revision = "20260826_10"
branch_labels = None
depends_on = None


def upgrade():
    if op.get_bind().dialect.name != "mysql":
        return
    op.alter_column("import_batches", "preview_json", existing_type=sa.Text(),
                    type_=LONGTEXT(), existing_nullable=False)


def downgrade():
    if op.get_bind().dialect.name != "mysql":
        return
    op.alter_column("import_batches", "preview_json", existing_type=LONGTEXT(),
                    type_=sa.Text(), existing_nullable=False)
