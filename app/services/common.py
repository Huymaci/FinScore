import re
from datetime import datetime

from flask import abort

EMAIL_RE = re.compile(r"^[^\s@]+@[^\s@]+\.[^\s@]+$")


class ValidationError(ValueError):
    pass


def require_fields(data, *fields):
    missing = [field for field in fields if data.get(field) in (None, "")]
    if missing:
        raise ValidationError("Thiếu trường: " + ", ".join(missing))


def parse_date(value, field="date"):
    try:
        return datetime.strptime(value, "%Y-%m-%d")
    except (TypeError, ValueError) as exc:
        raise ValidationError(f"{field} phải có định dạng YYYY-MM-DD") from exc


def user_account_ids(user_id):
    """Return the user's account ids so callers can filter on them directly.

    `Transaction.account.has(Account.ledger.has(user_id=...))` reads nicely but
    compiles to nested EXISTS subqueries, and MySQL cannot use
    ix_transactions_account_posted through them: EXPLAIN reports a full scan of
    every transaction (type ALL, key NULL) instead of a range scan. Resolving
    the ids in one cheap query and filtering with account_id IN (...) restores
    the index the DR-06 requirement exists to provide.
    """
    from sqlalchemy import select

    from app.extensions import db
    from app.models import Account, Ledger

    return list(db.session.scalars(
        select(Account.id).join(Ledger, Ledger.id == Account.ledger_id).where(Ledger.user_id == user_id)
    ))


def money(value):
    """Coerce a SQL aggregate to the signed integer VND that DR-01 mandates.

    MySQL returns DECIMAL for SUM() over a BIGINT column, while SQLite returns
    int. Two consequences follow on MySQL only, so the SQLite unit tests cannot
    see either: Decimal / float raises TypeError (this took down the FR-19
    burn-rate detector and every import confirm that followed it), and Flask
    serialises Decimal as a JSON *string*, so the API emitted "7065000" where
    the frontend expected 7065000. Normalising here keeps both correct.
    """
    return int(value or 0)


def owned_or_404(value):
    if value is None:
        abort(404)
    return value
