"""add default bank import templates

Revision ID: 20260824_04
Revises: 20260822_03
"""

import json

import sqlalchemy as sa
from alembic import op

revision = "20260824_04"
down_revision = "20260822_03"
branch_labels = None
depends_on = None


TEMPLATES = (
    ("VCB", "Vietcombank - số tiền có dấu", {"header_rows": 1, "date": 0, "description": 1, "amount": 2, "ref_no": 3, "date_format": "%d/%m/%Y"}),
    ("TCB", "Techcombank - ghi nợ/ghi có", {"header_rows": 1, "date": 0, "description": 1, "debit": 2, "credit": 3, "ref_no": 4, "date_format": "%d/%m/%Y"}),
    ("MB", "MB Bank - ghi nợ/ghi có", {"header_rows": 1, "date": 0, "ref_no": 1, "description": 2, "debit": 3, "credit": 4, "date_format": "%d/%m/%Y"}),
)


def upgrade():
    templates = sa.table(
        "import_templates",
        sa.column("bank_code", sa.String), sa.column("name", sa.String),
        sa.column("mapping_json", sa.Text), sa.column("active", sa.Boolean),
    )
    connection = op.get_bind()
    for bank_code, name, mapping in TEMPLATES:
        exists = connection.scalar(sa.select(sa.literal(1)).where(sa.exists().where(
            sa.and_(templates.c.bank_code == bank_code, templates.c.name == name)
        )))
        if not exists:
            op.bulk_insert(templates, [{
                "bank_code": bank_code, "name": name,
                "mapping_json": json.dumps(mapping), "active": True,
            }])


def downgrade():
    templates = sa.table("import_templates", sa.column("bank_code", sa.String), sa.column("name", sa.String))
    op.execute(templates.delete().where(templates.c.bank_code.in_([item[0] for item in TEMPLATES])))
