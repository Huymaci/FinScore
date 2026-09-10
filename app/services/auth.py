import re
from datetime import date, datetime, timedelta

from werkzeug.security import check_password_hash, generate_password_hash

from app.extensions import db
from app.models import AuditLog, Ledger, User, utcnow
from app.repositories import UserRepository

from .common import EMAIL_RE, ValidationError, require_fields


def normalize_email(value):
    if not isinstance(value, str):
        raise ValidationError("Email không hợp lệ")
    email = value.strip().lower()
    if len(email) > 254 or not EMAIL_RE.fullmatch(email):
        raise ValidationError("Email không hợp lệ")
    return email


def validate_full_name(value):
    if not isinstance(value, str):
        raise ValidationError("Họ tên không hợp lệ")
    full_name = value.strip()
    if not full_name:
        raise ValidationError("Họ tên không được để trống")
    if len(full_name) > 120:
        raise ValidationError("Họ tên không được vượt quá 120 ký tự")
    return full_name


def parse_adult_birth_date(value):
    try:
        birth_date = datetime.strptime(value, "%Y-%m-%d").date()
    except (TypeError, ValueError) as exc:
        raise ValidationError("Ngày sinh phải có định dạng YYYY-MM-DD") from exc
    today = date.today()
    age = today.year - birth_date.year - ((today.month, today.day) < (birth_date.month, birth_date.day))
    if age < 18:
        raise ValidationError("Người dùng phải đủ 18 tuổi")
    return birth_date


# Verified against when the email is unknown so that a missing account costs the
# same PBKDF2 work as a wrong password and the two cannot be told apart by
# response time (login is the unauthenticated brute-force / enumeration surface).
_ABSENT_USER_HASH = generate_password_hash("timing-equalizer", method="pbkdf2:sha256:600000")


def validate_password(password):
    if not isinstance(password, str):
        raise ValidationError("Mật khẩu không hợp lệ")
    classes = sum(bool(re.search(pattern, password)) for pattern in (r"[a-z]", r"[A-Z]", r"\d", r"[^A-Za-z0-9]"))
    if len(password) < 10 or classes < 3:
        raise ValidationError("Mật khẩu cần ít nhất 10 ký tự và 3 nhóm ký tự")


def register(data):
    require_fields(data, "email", "password", "full_name", "date_of_birth")
    email = normalize_email(data["email"])
    full_name = validate_full_name(data["full_name"])
    validate_password(data["password"])
    birth_date = parse_adult_birth_date(data["date_of_birth"])
    if UserRepository.by_email(email):
        raise ValidationError("Email đã tồn tại")
    user = User(
        email=email,
        full_name=full_name,
        date_of_birth=birth_date,
        consent=data.get("consent") is True,
        password_hash=generate_password_hash(data["password"], method="pbkdf2:sha256:600000"),
    )
    UserRepository.add(user)
    user.ledger = Ledger()
    db.session.commit()
    return user


def authenticate(email, password):
    user = UserRepository.by_email((email or "").strip().lower())
    now = utcnow()
    if user and user.locked_until and user.locked_until > now:
        raise ValidationError("Tài khoản đang tạm khóa")
    password_matches = check_password_hash(user.password_hash if user else _ABSENT_USER_HASH, password or "")
    if not user or not password_matches:
        if user:
            user.failed_logins += 1
            locked = user.failed_logins >= 5
            if locked:
                user.locked_until = now + timedelta(minutes=15)
            # FR-50/NFR-10: the admin console reports how many sign-ins failed
            # over a window. users.failed_logins cannot answer that -- it is a
            # streak counter reset to 0 by the next success -- so each failure
            # also lands in audit_logs. Only the user id is stored, never the
            # email or the attempted password.
            db.session.add(AuditLog(user_id=None, action=f"LOGIN_FAILED:{user.id}:{'LOCKED' if locked else 'OPEN'}"))
            db.session.commit()
        raise ValidationError("Email hoặc mật khẩu không đúng")
    user.failed_logins = 0
    user.locked_until = None
    user.last_login_at = now
    db.session.commit()
    return user


def change_password(user, current_password, new_password):
    if not isinstance(current_password, str) or not check_password_hash(user.password_hash, current_password):
        raise ValidationError("Mật khẩu hiện tại không đúng")
    validate_password(new_password)
    user.password_hash = generate_password_hash(new_password, method="pbkdf2:sha256:600000")
    db.session.commit()
