"""widen audit_logs.action so the erasure receipt fits

Revision ID: 20260825_08
Revises: 20260824_07

FR-05 writes a privacy-preserving deletion receipt of the form
`ACCOUNT_DELETED:<16-byte salt hex>:<sha256 hex>`, which is 113 characters.
The column was VARCHAR(100). SQLite does not enforce declared string lengths,
so the unit tests passed; MySQL in STRICT_TRANS_TABLES raises
(1406, "Data too long for column 'action'"), which made every admin-executed
erasure fail with a 500. Widened to 200 to leave headroom.
"""
import sqlalchemy as sa
from alembic import op

revision = "20260825_08"
down_revision = "20260824_07"
branch_labels = None
depends_on = None


def upgrade():
    with op.batch_alter_table("audit_logs") as batch_op:
        batch_op.alter_column("action", existing_type=sa.String(100), type_=sa.String(200), existing_nullable=False)


def downgrade():
    with op.batch_alter_table("audit_logs") as batch_op:
        batch_op.alter_column("action", existing_type=sa.String(200), type_=sa.String(100), existing_nullable=False)
