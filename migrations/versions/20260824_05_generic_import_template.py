"""add generic auto-detect import template

Revision ID: 20260824_05
Revises: 20260824_04
"""

import json

import sqlalchemy as sa
from alembic import op

revision = "20260824_05"
down_revision = "20260824_04"
branch_labels = None
depends_on = None


def upgrade():
    templates = sa.table(
        "import_templates",
        sa.column("bank_code", sa.String), sa.column("name", sa.String),
        sa.column("mapping_json", sa.Text), sa.column("active", sa.Boolean),
    )
    connection = op.get_bind()
    exists = connection.scalar(sa.select(sa.literal(1)).where(sa.exists().where(templates.c.bank_code == "AUTO")))
    if not exists:
        op.bulk_insert(templates, [{
            "bank_code": "AUTO", "name": "Tự động nhận diện CSV - ngân hàng khác",
            "mapping_json": json.dumps({"auto_detect": True}), "active": True,
        }])


def downgrade():
    templates = sa.table("import_templates", sa.column("bank_code", sa.String))
    op.execute(templates.delete().where(templates.c.bank_code == "AUTO"))
