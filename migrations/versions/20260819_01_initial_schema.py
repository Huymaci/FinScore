"""Initial schema for UC-01 through UC-05.

Revision ID: 20260819_01
Revises:
"""
import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects.mysql import BINARY, DATETIME

revision = "20260819_01"
down_revision = None
branch_labels = None
depends_on = None

# MY-02/MY-07: every table is InnoDB + utf8mb4/utf8mb4_0900_ai_ci.
TABLE_ARGS = {"mysql_engine": "InnoDB", "mysql_charset": "utf8mb4", "mysql_collate": "utf8mb4_0900_ai_ci"}
# DR-03: instants are DATETIME(6) holding UTC. TIMESTAMP is prohibited.
UTC = DATETIME(fsp=6)


def upgrade():
    op.create_table(
        "users",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column("email", sa.String(254), nullable=False, unique=True),
        sa.Column("password_hash", sa.String(255), nullable=False),
        sa.Column("full_name", sa.String(120), nullable=False),
        sa.Column("date_of_birth", sa.Date(), nullable=False),
        sa.Column("consent", sa.Boolean(), nullable=False),
        sa.Column("role", sa.String(20), nullable=False),
        sa.Column("failed_logins", sa.Integer(), nullable=False),
        sa.Column("locked_until", UTC),
        sa.Column("created_at", UTC, nullable=False),
        sa.Column("last_login_at", UTC),
        sa.Column("deletion_requested_at", UTC),
        # MY-08: enumerations are VARCHAR + CHECK, never the native ENUM type.
        sa.CheckConstraint("role IN ('USER','ADMIN')", name="ck_users_role"),
        **TABLE_ARGS,
    )
    op.create_table(
        "ledgers",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column("user_id", sa.Integer(), nullable=False, unique=True),
        # DR-04: erasure must be complete and verifiable.
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
        **TABLE_ARGS,
    )
    op.create_table(
        "categories",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column("owner_id", sa.Integer()),
        sa.Column("parent_id", sa.Integer()),
        sa.Column("name", sa.String(100), nullable=False),
        sa.Column("nature", sa.String(20)),
        sa.CheckConstraint(
            "nature IS NULL OR nature IN ('COMMITTED','SEMI_FIXED','DISCRETIONARY')",
            name="ck_categories_nature",
        ),
        sa.UniqueConstraint("owner_id", "name", name="uq_categories_owner_name"),
        sa.ForeignKeyConstraint(["owner_id"], ["users.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["parent_id"], ["categories.id"], ondelete="RESTRICT"),
        **TABLE_ARGS,
    )
    op.create_table(
        "accounts",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column("ledger_id", sa.Integer(), nullable=False),
        sa.Column("name", sa.String(100), nullable=False),
        sa.Column("type", sa.String(20), nullable=False),
        # DR-01/MY-09: money is signed BIGINT VND.
        sa.Column("opening_balance", sa.BigInteger(), nullable=False),
        sa.Column("bank_code", sa.String(20)),
        # FR-06: only the last four digits are ever stored.
        sa.Column("last_four", sa.String(4)),
        sa.Column("archived", sa.Boolean(), nullable=False),
        sa.CheckConstraint("type IN ('CASH','BANK')", name="ck_accounts_type"),
        sa.ForeignKeyConstraint(["ledger_id"], ["ledgers.id"], ondelete="CASCADE"),
        **TABLE_ARGS,
    )
    op.create_table(
        "import_templates",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column("bank_code", sa.String(20), nullable=False),
        sa.Column("name", sa.String(100), nullable=False),
        sa.Column("mapping_json", sa.Text(), nullable=False),
        sa.Column("active", sa.Boolean(), nullable=False),
        **TABLE_ARGS,
    )
    op.create_table(
        "transactions",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column("account_id", sa.Integer(), nullable=False),
        sa.Column("category_id", sa.Integer(), nullable=False),
        sa.Column("posted_at", UTC, nullable=False),
        sa.Column("amount", sa.BigInteger(), nullable=False),
        sa.Column("direction", sa.String(20), nullable=False),
        sa.Column("description", sa.String(500), nullable=False),
        sa.Column("source", sa.String(20), nullable=False),
        sa.Column("ref_no", sa.String(100), nullable=False),
        # MY-04: raw SHA-256 digest in BINARY(32), not VARCHAR(64).
        # DR-02: uniqueness enforced by the database, not only by service code.
        sa.Column("dedup_key", BINARY(32), unique=True),
        sa.CheckConstraint("amount > 0", name="ck_transactions_amount"),
        sa.CheckConstraint("direction IN ('IN','OUT')", name="ck_transactions_direction"),
        sa.ForeignKeyConstraint(["account_id"], ["accounts.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["category_id"], ["categories.id"], ondelete="RESTRICT"),
        **TABLE_ARGS,
    )
    # DR-06
    op.create_index("ix_transactions_account_posted", "transactions", ["account_id", "posted_at"])
    op.create_table(
        "import_batches",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column("user_id", sa.Integer(), nullable=False),
        sa.Column("account_id", sa.Integer(), nullable=False),
        sa.Column("template_id", sa.Integer(), nullable=False),
        sa.Column("filename", sa.String(255), nullable=False),
        sa.Column("status", sa.String(20), nullable=False),
        sa.Column("preview_json", sa.Text(), nullable=False),
        sa.Column("created_at", UTC, nullable=False),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["account_id"], ["accounts.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["template_id"], ["import_templates.id"], ondelete="RESTRICT"),
        **TABLE_ARGS,
    )
    op.create_table(
        "import_errors",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column("batch_id", sa.Integer(), nullable=False),
        sa.Column("row_number", sa.Integer(), nullable=False),
        sa.Column("reason", sa.String(500), nullable=False),
        sa.ForeignKeyConstraint(["batch_id"], ["import_batches.id"], ondelete="CASCADE"),
        **TABLE_ARGS,
    )
    op.create_table(
        "audit_logs",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column("user_id", sa.Integer()),
        sa.Column("action", sa.String(100), nullable=False),
        sa.Column("created_at", UTC, nullable=False),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
        **TABLE_ARGS,
    )


def downgrade():
    op.drop_table("audit_logs")
    op.drop_table("import_errors")
    op.drop_table("import_batches")
    op.drop_index("ix_transactions_account_posted", table_name="transactions")
    op.drop_table("transactions")
    op.drop_table("import_templates")
    op.drop_table("accounts")
    op.drop_table("categories")
    op.drop_table("ledgers")
    op.drop_table("users")
