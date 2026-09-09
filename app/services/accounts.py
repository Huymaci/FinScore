from sqlalchemy import case, delete, func, select

from app.extensions import db
from app.models import Account, ImportBatch, ImportError, Transaction
from app.repositories import AccountRepository

from .common import ValidationError, owned_or_404, require_fields


def current_balances(accounts):
    """Opening balances plus all saved inflows minus all saved outflows."""
    balances = {account.id: account.opening_balance for account in accounts}
    if not balances:
        return balances
    totals = db.session.execute(
        select(Transaction.account_id, func.sum(case(
            (Transaction.direction == "IN", Transaction.amount),
            else_=-Transaction.amount,
        )))
        .where(Transaction.account_id.in_(balances))
        .group_by(Transaction.account_id)
    )
    for account_id, net in totals:
        balances[account_id] += int(net or 0)
    return balances


def _values(data, include_default=True):
    require_fields(data, "name", "type", "opening_balance")
    account_type = data["type"].upper()
    if account_type not in {"CASH", "BANK"}:
        raise ValidationError("Loại tài khoản phải là CASH hoặc BANK")
    try:
        balance = int(data["opening_balance"])
    except (TypeError, ValueError) as exc:
        raise ValidationError("Số dư đầu kỳ phải là số nguyên VND") from exc
    last_four = data.get("last_four")
    if account_type == "BANK" and (not last_four or len(last_four) != 4 or not last_four.isdigit()):
        raise ValidationError("Tài khoản ngân hàng chỉ lưu đúng 4 số cuối")
    if any(key in data for key in ("account_number", "credentials", "password", "otp")):
        raise ValidationError("Không được gửi số tài khoản đầy đủ hoặc thông tin xác thực ngân hàng")
    include_in_safe_to_spend = data.get("include_in_safe_to_spend", include_default)
    if not isinstance(include_in_safe_to_spend, bool):
        raise ValidationError("include_in_safe_to_spend phải là boolean")
    return {
        "name": data["name"].strip(), "type": account_type,
        "opening_balance": balance, "bank_code": data.get("bank_code"),
        "last_four": last_four if account_type == "BANK" else None,
        "include_in_safe_to_spend": include_in_safe_to_spend,
    }


def create(user, data):
    account = Account(ledger_id=user.ledger.id, **_values(data))
    db.session.add(account)
    db.session.commit()
    return account


def update(user, account_id, data):
    account = owned_or_404(AccountRepository.owned(account_id, user.id))
    for key, value in _values(data, account.include_in_safe_to_spend).items():
        setattr(account, key, value)
    db.session.commit()
    return account


def archive(user, account_id):
    account = owned_or_404(AccountRepository.owned(account_id, user.id))
    account.archived = True
    db.session.commit()


def restore(user, account_id):
    account = owned_or_404(AccountRepository.owned(account_id, user.id))
    account.archived = False
    db.session.commit()
    return account


def permanently_delete(user, account_id):
    """Delete an archived account and all data that belongs to it atomically.

    Requiring the archive step first prevents an active account from being
    erased by a single accidental request.  The dependent rows are removed
    explicitly so this behaves consistently even when SQLite foreign-key
    cascades are disabled in tests or local development.
    """
    account = owned_or_404(AccountRepository.owned(account_id, user.id))
    if not account.archived:
        raise ValidationError("Chỉ có thể xóa vĩnh viễn tài khoản đã được xóa trước đó")

    batch_ids = select(ImportBatch.id).where(ImportBatch.account_id == account.id)
    db.session.execute(delete(ImportError).where(ImportError.batch_id.in_(batch_ids)))
    db.session.execute(delete(ImportBatch).where(ImportBatch.account_id == account.id))
    db.session.execute(delete(Transaction).where(Transaction.account_id == account.id))
    db.session.delete(account)
    db.session.commit()
