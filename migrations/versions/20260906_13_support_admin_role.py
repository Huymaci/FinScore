"""add delegated support administrator role

Revision ID: 20260906_13
Revises: 20260905_12
"""
from alembic import op

revision = "20260906_13"
down_revision = "20260905_12"
branch_labels = None
depends_on = None


def upgrade():
    with op.batch_alter_table("users") as batch_op:
        batch_op.drop_constraint("ck_users_role", type_="check")
        batch_op.create_check_constraint("ck_users_role", "role IN ('USER','ADMIN','SUPPORT_ADMIN')")


def downgrade():
    op.execute("UPDATE users SET role = 'USER' WHERE role = 'SUPPORT_ADMIN'")
    with op.batch_alter_table("users") as batch_op:
        batch_op.drop_constraint("ck_users_role", type_="check")
        batch_op.create_check_constraint("ck_users_role", "role IN ('USER','ADMIN')")
