"""mark accounts included in Safe-to-Spend

Revision ID: 20260822_03
Revises: 20260819_02
"""

import sqlalchemy as sa
from alembic import op

revision = "20260822_03"
down_revision = "20260819_02"
branch_labels = None
depends_on = None


def upgrade():
    op.add_column(
        "accounts",
        sa.Column("include_in_safe_to_spend", sa.Boolean(), nullable=False, server_default=sa.true()),
    )
    op.execute(
        sa.text("UPDATE accounts SET include_in_safe_to_spend = :included WHERE bank_code = :bank_code")
        .bindparams(included=False, bank_code="VPB")
    )


def downgrade():
    op.drop_column("accounts", "include_in_safe_to_spend")
