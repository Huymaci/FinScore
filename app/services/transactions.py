from app.extensions import db
from app.models import Category, Transaction
from app.repositories import AccountRepository, CategoryRepository, TransactionRepository

from .common import ValidationError, owned_or_404, parse_date, require_fields


def _values(user_id, data):
    require_fields(data, "date", "amount", "direction", "account_id")
    direction = data["direction"].upper()
    if direction not in {"IN", "OUT"}:
        raise ValidationError("direction phải là IN hoặc OUT")
    try:
        amount = int(data["amount"])
        account_id = int(data["account_id"])
        category_id = int(data["category_id"]) if data.get("category_id") else None
    except (TypeError, ValueError) as exc:
        raise ValidationError("amount, account_id và category_id phải là số nguyên") from exc
    if amount <= 0:
        raise ValidationError("Số tiền phải lớn hơn 0")
    owned_or_404(AccountRepository.owned(account_id, user_id, include_archived=False))
    if category_id is None and direction == "IN":
        category = db.session.query(Category).filter(
            Category.name == "Thu nhập",
            (Category.owner_id.is_(None)) | (Category.owner_id == user_id),
            Category.nature.is_not(None),
        ).order_by(Category.owner_id, Category.id).first()
        if category is None:
            category = Category(owner_id=user_id, name="Thu nhập", nature="COMMITTED")
            db.session.add(category)
            db.session.flush()
        category_id = category.id
    if category_id is None:
        raise ValidationError("Vui lòng chọn danh mục khoản chi")
    owned_or_404(CategoryRepository.available(category_id, user_id))
    description = str(data.get("description", "")).strip()
    note = str(data.get("note", "")).strip()
    if len(description) > 500 or len(note) > 500:
        raise ValidationError("Mô tả và ghi chú không được vượt quá 500 ký tự")
    return {"posted_at": parse_date(data["date"]), "amount": amount, "direction": direction, "account_id": account_id, "category_id": category_id, "description": description, "note": note, "source": "MANUAL"}


def create(user, data):
    transaction = Transaction(**_values(user.id, data))
    db.session.add(transaction)
    db.session.commit()
    return transaction


def update(user, transaction_id, data):
    transaction = owned_or_404(TransactionRepository.owned(transaction_id, user.id))
    for key, value in _values(user.id, data).items():
        setattr(transaction, key, value)
    db.session.commit()
    return transaction


def delete(user, transaction_id):
    transaction = owned_or_404(TransactionRepository.owned(transaction_id, user.id))
    db.session.delete(transaction)
    db.session.commit()
