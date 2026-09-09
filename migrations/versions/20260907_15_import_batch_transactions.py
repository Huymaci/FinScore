"""associate imported transactions with their originating batch

Revision ID: 20260907_15
Revises: 20260906_14
"""

import json

import sqlalchemy as sa
from alembic import op

revision = "20260907_15"
down_revision = "20260906_14"
branch_labels = None
depends_on = None


def _preview_keys(preview_json):
    try:
        rows = json.loads(preview_json).get("rows", [])
    except (AttributeError, TypeError, ValueError):
        return []
    keys = []
    for row in rows:
        try:
            keys.append(bytes.fromhex(row["dedup_key"]))
        except (KeyError, TypeError, ValueError):
            continue
    return keys


def upgrade():
    with op.batch_alter_table("transactions") as batch_op:
        batch_op.add_column(sa.Column("import_batch_id", sa.Integer(), nullable=True))
        batch_op.create_index("ix_transactions_import_batch", ["import_batch_id"], unique=False)
        batch_op.create_foreign_key(
            "fk_transactions_import_batch_id",
            "import_batches",
            ["import_batch_id"],
            ["id"],
            ondelete="SET NULL",
        )

    connection = op.get_bind()
    batches = sa.table(
        "import_batches",
        sa.column("id", sa.Integer),
        sa.column("account_id", sa.Integer),
        sa.column("status", sa.String),
        sa.column("preview_json", sa.Text),
        sa.column("created_at", sa.DateTime),
    )
    transactions = sa.table(
        "transactions",
        sa.column("import_batch_id", sa.Integer),
        sa.column("account_id", sa.Integer),
        sa.column("source", sa.String),
        sa.column("dedup_key", sa.LargeBinary),
    )

    # Newer batches claim their own rows first. This correctly repairs the
    # historical case where rejected rows from an older preview were imported
    # by a later batch using the same statement file.
    committed = connection.execute(
        sa.select(batches.c.id, batches.c.account_id, batches.c.preview_json)
        .where(batches.c.status == "COMMITTED")
        .order_by(batches.c.created_at.desc(), batches.c.id.desc())
    )
    for batch in committed:
        keys = _preview_keys(batch.preview_json)
        if not keys:
            continue
        connection.execute(
            transactions.update()
            .where(
                transactions.c.import_batch_id.is_(None),
                transactions.c.account_id == batch.account_id,
                transactions.c.source == "IMPORT",
                transactions.c.dedup_key.in_(keys),
            )
            .values(import_batch_id=batch.id)
        )


def downgrade():
    with op.batch_alter_table("transactions") as batch_op:
        batch_op.drop_constraint("fk_transactions_import_batch_id", type_="foreignkey")
        batch_op.drop_index("ix_transactions_import_batch")
        batch_op.drop_column("import_batch_id")
