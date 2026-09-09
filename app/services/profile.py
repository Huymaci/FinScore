import csv
import hashlib
import io
import json
import os
import secrets
import zipfile
from pathlib import Path

from flask import current_app
from sqlalchemy import delete, select
from sqlalchemy.exc import IntegrityError

from app.extensions import db
from app.models import (
    Account,
    Alert,
    AuditLog,
    Budget,
    Category,
    HabitChallenge,
    ImportBatch,
    ImportError,
    Ledger,
    SupportReport,
    Transaction,
)
from app.repositories import UserRepository

from .auth import normalize_email, parse_adult_birth_date, validate_full_name
from .common import ValidationError

MAX_AVATAR_BYTES = 2 * 1024 * 1024
AVATAR_TYPES = {
    "jpeg": "image/jpeg",
    "png": "image/png",
    "webp": "image/webp",
}


def update_profile(user, data):
    changes = {}
    if "full_name" in data:
        changes["full_name"] = validate_full_name(data["full_name"])
    if "email" in data:
        email = normalize_email(data["email"])
        existing = UserRepository.by_email(email)
        if existing and existing.id != user.id:
            raise ValidationError("Email đã tồn tại")
        changes["email"] = email
    if "date_of_birth" in data:
        changes["date_of_birth"] = parse_adult_birth_date(data["date_of_birth"])
    if "consent" in data:
        if not isinstance(data["consent"], bool):
            raise ValidationError("Trạng thái đồng ý phải là true hoặc false")
        changes["consent"] = data["consent"]
    for field, value in changes.items():
        setattr(user, field, value)
    try:
        db.session.commit()
    except IntegrityError as exc:
        db.session.rollback()
        raise ValidationError("Email đã tồn tại") from exc
    return user


def _avatar_kind(content):
    if content.startswith(b"\x89PNG\r\n\x1a\n"):
        return "png"
    if content.startswith(b"\xff\xd8\xff"):
        return "jpeg"
    if len(content) >= 12 and content.startswith(b"RIFF") and content[8:12] == b"WEBP":
        return "webp"
    raise ValidationError("Ảnh đại diện phải là tệp PNG, JPEG hoặc WebP hợp lệ")


def avatar_directory():
    return Path(current_app.config["UPLOAD_FOLDER"]) / "avatars"


def avatar_path(user):
    filename = user.avatar_filename
    if not filename or Path(filename).name != filename:
        return None
    return avatar_directory() / filename


def avatar_mimetype(user):
    suffix = Path(user.avatar_filename or "").suffix.lower().lstrip(".")
    return AVATAR_TYPES.get(suffix, "application/octet-stream")


def _unlink_avatar(path):
    if not path:
        return
    try:
        path.unlink(missing_ok=True)
    except OSError:
        current_app.logger.warning("Could not remove obsolete avatar file %s", path, exc_info=True)


def save_avatar(user, uploaded):
    if not uploaded or not uploaded.filename:
        raise ValidationError("Vui lòng chọn ảnh đại diện")
    content = uploaded.stream.read(MAX_AVATAR_BYTES + 1)
    if not content:
        raise ValidationError("Ảnh đại diện không được để trống")
    if len(content) > MAX_AVATAR_BYTES:
        raise ValidationError("Ảnh đại diện không được vượt quá 2 MB")
    kind = _avatar_kind(content)
    directory = avatar_directory()
    directory.mkdir(parents=True, exist_ok=True)
    filename = f"{secrets.token_hex(24)}.{kind}"
    destination = directory / filename
    temporary = directory / f".{filename}.tmp"
    previous = avatar_path(user)
    try:
        with temporary.open("xb") as output:
            output.write(content)
        os.replace(temporary, destination)
        user.avatar_filename = filename
        db.session.commit()
    except Exception:
        db.session.rollback()
        _unlink_avatar(temporary)
        _unlink_avatar(destination)
        raise
    if previous and previous != destination:
        _unlink_avatar(previous)
    return user


def remove_avatar(user):
    previous = avatar_path(user)
    user.avatar_filename = None
    db.session.commit()
    _unlink_avatar(previous)


def export_data(user):
    accounts = user.ledger.accounts
    account_ids = {account.id for account in accounts}
    transactions = list(db.session.query(Transaction).filter(Transaction.account_id.in_(account_ids))) if account_ids else []
    categories = list(db.session.scalars(select(Category).where(Category.owner_id == user.id)))
    budgets = list(db.session.scalars(select(Budget).where(Budget.user_id == user.id)))
    alerts = list(db.session.scalars(select(Alert).where(Alert.user_id == user.id)))
    challenges = list(db.session.scalars(select(HabitChallenge).where(HabitChallenge.user_id == user.id)))
    imports = list(db.session.scalars(select(ImportBatch).where(ImportBatch.user_id == user.id)))
    import_ids = [item.id for item in imports]
    import_errors = list(db.session.scalars(select(ImportError).where(ImportError.batch_id.in_(import_ids)))) if import_ids else []
    audit_logs = list(db.session.scalars(select(AuditLog).where(AuditLog.user_id == user.id)))
    support_reports = list(db.session.scalars(select(SupportReport).where(SupportReport.user_id == user.id)))
    payload = {
        "profile": {"email": user.email, "full_name": user.full_name, "date_of_birth": user.date_of_birth.isoformat(), "consent": user.consent},
        "accounts": [{
            "id": a.id, "name": a.name, "type": a.type,
            "opening_balance": a.opening_balance, "bank_code": a.bank_code,
            "last_four": a.last_four, "archived": a.archived,
            "include_in_safe_to_spend": a.include_in_safe_to_spend,
        } for a in accounts],
        "transactions": [{"id": t.id, "date": t.posted_at.date().isoformat(), "amount": t.amount, "direction": t.direction, "account_id": t.account_id, "category_id": t.category_id, "description": t.description, "note": t.note, "import_batch_id": t.import_batch_id} for t in transactions],
        "custom_categories": [{"id": x.id, "parent_id": x.parent_id, "name": x.name, "nature": x.nature} for x in categories],
        "budgets": [{"id": x.id, "category_id": x.category_id, "month": x.month.isoformat(), "amount": x.amount} for x in budgets],
        "alerts": [{"id": x.id, "category_id": x.category_id, "kind": x.kind, "severity": x.severity, "explanation": x.explanation, "suggested_action": x.suggested_action, "status": x.status, "triggered_at": x.triggered_at.isoformat()} for x in alerts],
        "habit_challenges": [{"id": x.id, "category_id": x.category_id, "habit_name": x.habit_name, "baseline_count": x.baseline_count, "target_count": x.target_count, "period_start": x.period_start.isoformat() if x.period_start else None, "period_end": x.period_end.isoformat() if x.period_end else None, "actual_count": x.actual_count, "saved_amount": x.saved_amount, "status": x.status} for x in challenges],
        "imports": [{"id": x.id, "account_id": x.account_id, "template_id": x.template_id, "filename": x.filename, "status": x.status, "created_at": x.created_at.isoformat()} for x in imports],
        "import_errors": [{"batch_id": x.batch_id, "row_number": x.row_number, "reason": x.reason} for x in import_errors],
        "audit_logs": [{"action": x.action, "created_at": x.created_at.isoformat()} for x in audit_logs],
        "support_reports": [{
            "id": x.id, "subject": x.subject, "message": x.message,
            "status": x.status, "created_at": x.created_at.isoformat(),
            "resolved_at": x.resolved_at.isoformat() if x.resolved_at else None,
        } for x in support_reports],
    }
    csv_buffer = io.StringIO()
    writer = csv.DictWriter(csv_buffer, fieldnames=["id", "date", "amount", "direction", "account_id", "category_id", "description", "note", "import_batch_id"])
    writer.writeheader()
    writer.writerows(payload["transactions"])
    archive = io.BytesIO()
    with zipfile.ZipFile(archive, "w", zipfile.ZIP_DEFLATED) as bundle:
        bundle.writestr("smartfinance.json", json.dumps(payload, ensure_ascii=False, indent=2))
        bundle.writestr("transactions.csv", csv_buffer.getvalue())
        picture = avatar_path(user)
        if picture and picture.is_file():
            bundle.write(picture, f"profile-avatar{picture.suffix}")
    archive.seek(0)
    return archive


def delete_account(user):
    # Explicit order makes erasure verifiable even before relying on InnoDB cascades.
    picture = avatar_path(user)
    account_ids = list(db.session.scalars(select(Account.id).where(Account.ledger.has(user_id=user.id))))
    batch_ids = list(db.session.scalars(select(ImportBatch.id).where(ImportBatch.user_id == user.id)))
    if batch_ids:
        db.session.execute(delete(ImportError).where(ImportError.batch_id.in_(batch_ids)))
    if account_ids:
        db.session.execute(delete(Transaction).where(Transaction.account_id.in_(account_ids)))
    db.session.execute(delete(ImportBatch).where(ImportBatch.user_id == user.id))
    db.session.execute(delete(HabitChallenge).where(HabitChallenge.user_id == user.id))
    db.session.execute(delete(Alert).where(Alert.user_id == user.id))
    db.session.execute(delete(Budget).where(Budget.user_id == user.id))
    db.session.execute(delete(SupportReport).where(SupportReport.user_id == user.id))
    db.session.execute(delete(Category).where(Category.owner_id == user.id))
    db.session.execute(delete(AuditLog).where(AuditLog.user_id == user.id))
    if account_ids:
        db.session.execute(delete(Account).where(Account.id.in_(account_ids)))
    db.session.execute(delete(Ledger).where(Ledger.user_id == user.id))
    salt = secrets.token_bytes(16)
    deleted_email_hash = hashlib.sha256(salt + user.email.encode("utf-8")).hexdigest()
    db.session.delete(user)
    db.session.flush()
    db.session.add(AuditLog(user_id=None, action=f"ACCOUNT_DELETED:{salt.hex()}:{deleted_email_hash}"))
    db.session.commit()
    _unlink_avatar(picture)
