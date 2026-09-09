from sqlalchemy import select

from app.extensions import db
from app.models import AuditLog, SupportReport, utcnow

from .common import ValidationError


def _clean_text(value, field, *, minimum, maximum):
    text = str(value or "").strip()
    if len(text) < minimum:
        raise ValidationError(f"{field} phải có ít nhất {minimum} ký tự")
    if len(text) > maximum:
        raise ValidationError(f"{field} không được vượt quá {maximum} ký tự")
    return text


def create_report(user_id, data):
    report = SupportReport(
        user_id=user_id,
        subject=_clean_text(data.get("subject"), "Tiêu đề", minimum=3, maximum=160),
        message=_clean_text(data.get("message"), "Nội dung", minimum=10, maximum=4000),
    )
    db.session.add(report)
    db.session.commit()
    return report


def list_for_user(user_id, page=1, per_page=20):
    statement = select(SupportReport).where(SupportReport.user_id == user_id).order_by(
        SupportReport.created_at.desc(), SupportReport.id.desc()
    )
    return db.paginate(statement, page=page, per_page=per_page, error_out=False)


def list_for_admin(status="ALL", page=1, per_page=20):
    if status not in {"ALL", "OPEN", "RESOLVED"}:
        raise ValidationError("Trạng thái phải là ALL, OPEN hoặc RESOLVED")
    statement = select(SupportReport)
    if status != "ALL":
        statement = statement.where(SupportReport.status == status)
    statement = statement.order_by(SupportReport.created_at.desc(), SupportReport.id.desc())
    return db.paginate(statement, page=page, per_page=per_page, error_out=False)


def set_status(report_id, status):
    if status not in {"OPEN", "RESOLVED"}:
        raise ValidationError("Trạng thái phải là OPEN hoặc RESOLVED")
    report = db.session.get(SupportReport, report_id)
    if not report:
        from flask import abort

        abort(404)
    report.status = status
    report.resolved_at = utcnow() if status == "RESOLVED" else None
    db.session.add(AuditLog(user_id=None, action=f"ADMIN_SUPPORT_REPORT_{status}:{report.id}"))
    db.session.commit()
    return report
