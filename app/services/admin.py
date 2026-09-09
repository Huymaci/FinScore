import secrets
from datetime import datetime, timedelta

from sqlalchemy import case, func, or_, select
from werkzeug.security import generate_password_hash

from app.extensions import db
from app.models import AuditLog, ImportBatch, ImportError, ImportTemplate, User, utcnow

from .auth import validate_password
from .common import ValidationError, money
from .profile import delete_account


def search_users(query="", page=1, per_page=20, include_support_admins=False, status="ALL", role="ALL"):
    roles = ["USER", "SUPPORT_ADMIN"] if include_support_admins else ["USER"]
    statement = select(User).where(User.role.in_(roles))
    if query:
        statement = statement.where((User.email.contains(query.lower())) | (User.full_name.contains(query)))
    now = utcnow()
    if status == "ACTIVE":
        statement = statement.where(or_(User.locked_until.is_(None), User.locked_until <= now))
    elif status == "LOCKED":
        statement = statement.where(User.locked_until > now)
    if role in roles:
        statement = statement.where(User.role == role)
    return db.paginate(statement.order_by(User.created_at.desc()), page=page, per_page=per_page, error_out=False)


def metadata(user, can_manage_role=False):
    now = utcnow()
    return {"id": user.id, "email": user.email, "full_name": user.full_name, "role": user.role, "can_manage_role": can_manage_role, "status": "LOCKED" if user.locked_until and user.locked_until > now else "ACTIVE", "registration_date": user.created_at.isoformat(), "last_login": user.last_login_at.isoformat() if user.last_login_at else None, "deletion_requested": user.deletion_requested_at.isoformat() if user.deletion_requested_at else None}


def change_role(user_id, role):
    if role not in {"USER", "SUPPORT_ADMIN"}:
        raise ValidationError("Quyền quản trị không hợp lệ")
    user = db.session.scalar(select(User).where(User.id == user_id, User.role.in_(["USER", "SUPPORT_ADMIN"])))
    if not user:
        from flask import abort
        abort(404)
    previous_role = user.role
    user.role = role
    db.session.add(AuditLog(user_id=None, action=f"ADMIN_CHANGE_ROLE:{user.id}:{previous_role}->{role}"))
    db.session.commit()
    return user


def _user(user_id):
    user = db.session.scalar(select(User).where(User.id == user_id, User.role == "USER"))
    if not user:
        from flask import abort
        abort(404)
    return user


def lock(user_id, locked):
    user = _user(user_id)
    user.locked_until = datetime(9999, 12, 31) if locked else None
    user.failed_logins = 0
    db.session.add(AuditLog(user_id=None, action=f"ADMIN_{'LOCK' if locked else 'UNLOCK'}_USER:{user.id}"))
    db.session.commit()


def reset_password(user_id):
    user = _user(user_id)
    temporary = secrets.token_urlsafe(12) + "A1!"
    validate_password(temporary)
    user.password_hash = generate_password_hash(temporary, method="pbkdf2:sha256:600000")
    db.session.add(AuditLog(user_id=None, action=f"ADMIN_RESET_PASSWORD:{user.id}"))
    db.session.commit()
    return temporary


def execute_deletion(user_id, require_request=True):
    user = _user(user_id)
    if require_request and not user.deletion_requested_at:
        raise ValidationError("Người dùng chưa yêu cầu xóa tài khoản")
    delete_account(user)


def toggle(model, object_id, active):
    item = db.session.get(model, object_id)
    if not item:
        from flask import abort
        abort(404)
    item.active = active is True
    db.session.commit()
    return item


def operations():
    total_users = db.session.scalar(select(func.count()).select_from(User).where(User.role == "USER")) or 0
    if total_users < 5:
        return {"suppressed": True, "reason": "Số người dùng nhỏ hơn 5", "active_users": None, "import_success_rate_by_bank": None, "error_count": None, "nightly_job_status": None}
    active_since = utcnow() - timedelta(days=30)
    active = db.session.scalar(select(func.count()).select_from(User).where(User.role == "USER", User.last_login_at >= active_since)) or 0
    imports = db.session.execute(select(ImportTemplate.bank_code, func.count(ImportBatch.id), func.sum(case((ImportBatch.status == "COMMITTED", 1), else_=0))).join(ImportBatch, ImportBatch.template_id == ImportTemplate.id).group_by(ImportTemplate.bank_code)).all()
    rates = {bank: round(money(success) * 100 / total, 1) if total else 0 for bank, total, success in imports}
    error_count = db.session.scalar(select(func.count()).select_from(ImportError)) or 0
    last_job = db.session.scalar(select(AuditLog).where(AuditLog.action.like("NIGHTLY_JOB:%")).order_by(AuditLog.created_at.desc()))
    return {"suppressed": False, "active_users": active, "import_success_rate_by_bank": rates, "error_count": error_count, "nightly_job_status": last_job.action.split(":", 1)[1] if last_job else "NEVER_RUN"}


def audit_logs(page=1, per_page=50):
    return db.paginate(select(AuditLog).order_by(AuditLog.created_at.desc()), page=page, per_page=per_page, error_out=False)
