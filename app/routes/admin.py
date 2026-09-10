from functools import wraps

from flask import Blueprint, abort, jsonify, request
from flask_login import current_user, login_required

from app.models import CategorizationRule, ImportTemplate
from app.services import admin as service
from app.services import support as support_service

from .helpers import json_body, validation_response
from .support import support_report_json

admin_bp = Blueprint("admin", __name__, url_prefix="/admin")


def admin_required(function):
    @wraps(function)
    @login_required
    def wrapped(*args, **kwargs):
        if current_user.role not in {"ADMIN", "SUPPORT_ADMIN"}:
            abort(403)
        return function(*args, **kwargs)
    return wrapped


def primary_admin_required(function):
    @wraps(function)
    @admin_required
    def wrapped(*args, **kwargs):
        if current_user.role != "ADMIN":
            abort(403)
        return function(*args, **kwargs)
    return wrapped


@admin_bp.get("/users")
@admin_required
def users():
    page = service.search_users(request.args.get("q", ""), request.args.get("page", 1, type=int), min(request.args.get("per_page", 20, type=int), 100), include_support_admins=current_user.role == "ADMIN", status=request.args.get("status", "ALL"), role=request.args.get("role", "ALL"))
    return jsonify(items=[service.metadata(item, can_manage_role=current_user.role == "ADMIN") for item in page.items], total=page.total, page=page.page, pages=page.pages)


@admin_bp.patch("/users/<int:user_id>/role")
@primary_admin_required
def change_user_role(user_id):
    user = service.change_role(user_id, json_body().get("role"))
    return jsonify(service.metadata(user, can_manage_role=True))


@admin_bp.post("/users/<int:user_id>/lock")
@admin_required
def lock_user(user_id):
    service.lock(user_id, True)
    return jsonify(message="Đã khóa")


@admin_bp.post("/users/<int:user_id>/unlock")
@admin_required
def unlock_user(user_id):
    service.lock(user_id, False)
    return jsonify(message="Đã mở khóa")


@admin_bp.post("/users/<int:user_id>/reset-password")
@admin_required
def reset_password(user_id):
    return jsonify(temporary_password=service.reset_password(user_id))


# FR-48/FR-47: executing an account deletion is a primary-ADMIN action. A
# delegated SUPPORT_ADMIN handles day-to-day support (metadata, lock/unlock,
# temporary password, support reports) but not the irreversible PII erasure
# NFR-11 governs; both /users/<id> and /users/<id>/violation are ADMIN-only.
@admin_bp.delete("/users/<int:user_id>")
@primary_admin_required
def delete_user(user_id):
    return validation_response(lambda: (service.execute_deletion(user_id), jsonify(message="Đã xóa dữ liệu cá nhân"))[1])


@admin_bp.delete("/users/<int:user_id>/violation")
@primary_admin_required
def delete_violating_user(user_id):
    service.execute_deletion(user_id, require_request=False)
    return jsonify(message="Đã xóa tài khoản vi phạm")


@admin_bp.get("/import-config")
@primary_admin_required
def import_config():
    from app.extensions import db
    return jsonify(
        templates=[{"id": x.id, "bank_code": x.bank_code, "name": x.name, "active": x.active} for x in db.session.query(ImportTemplate).all()],
        rules=[{"id": x.id, "pattern": x.pattern, "category_id": x.category_id, "priority": x.priority, "active": x.active} for x in db.session.query(CategorizationRule).all()],
    )


@admin_bp.patch("/import-config/<kind>/<int:object_id>")
@primary_admin_required
def toggle_import_config(kind, object_id):
    model = ImportTemplate if kind == "template" else CategorizationRule if kind == "rule" else None
    if not model:
        abort(404)
    item = service.toggle(model, object_id, json_body().get("active"))
    return jsonify(id=item.id, active=item.active)


@admin_bp.get("/operations")
@primary_admin_required
def operations():
    return jsonify(service.operations())


@admin_bp.get("/audit-logs")
@primary_admin_required
def audit_logs():
    page = service.audit_logs(request.args.get("page", 1, type=int))
    return jsonify(items=[{"id": x.id, "action": x.action, "created_at": x.created_at.isoformat()} for x in page.items], total=page.total)


@admin_bp.get("/support-reports")
@admin_required
def support_reports():
    def action():
        page_number = max(request.args.get("page", 1, type=int), 1)
        per_page = max(1, min(request.args.get("per_page", 20, type=int), 100))
        page = support_service.list_for_admin(request.args.get("status", "ALL"), page_number, per_page)
        return jsonify(
            items=[support_report_json(item, include_user=True) for item in page.items],
            total=page.total,
            page=page.page,
            pages=page.pages,
        )

    return validation_response(action)


@admin_bp.patch("/support-reports/<int:report_id>")
@admin_required
def update_support_report(report_id):
    return validation_response(
        lambda: jsonify(support_report_json(
            support_service.set_status(report_id, json_body().get("status")),
            include_user=True,
        ))
    )


@admin_bp.get("/system-status")
@primary_admin_required
def system_status():
    return jsonify(service.system_status())


@admin_bp.get("/system-logs")
@primary_admin_required
def system_logs():
    items, page = service.system_logs(
        page=max(request.args.get("page", 1, type=int), 1),
        per_page=max(1, min(request.args.get("per_page", 25, type=int), 100)),
        category=request.args.get("category", "ALL"),
        severity=request.args.get("severity", "ALL"),
        query=request.args.get("q", "").strip(),
        hours=request.args.get("hours", type=int),
    )
    return jsonify(items=items, total=page.total, page=page.page, pages=max(page.pages, 1))


@admin_bp.get("/errors")
@primary_admin_required
def error_monitor():
    from app.services import metrics
    snapshot = metrics.snapshot()
    handled = request.args.get("handled", "ALL")
    groups = snapshot["error_groups"]
    if handled == "OPEN":
        groups = [group for group in groups if not group["handled"]]
    elif handled == "HANDLED":
        groups = [group for group in groups if group["handled"]]
    return jsonify(items=groups, recent=metrics.recent_errors(50),
                   partial=snapshot["partial"], since=snapshot["since"])


@admin_bp.patch("/errors")
@primary_admin_required
def update_error_state():
    from app.services import metrics
    body = json_body()
    updated = metrics.mark_handled(body.get("method", ""), body.get("rule", ""),
                                   body.get("status", 0), bool(body.get("handled", True)))
    if not updated:
        abort(404)
    return jsonify(message="Đã cập nhật trạng thái lỗi")


# FR-51/NFR-09: the batch list carries no filename and no account name. A
# statement filename regularly contains the account holder's own name, which
# is exactly the identified data the console must not surface.
@admin_bp.get("/import-batches")
@primary_admin_required
def import_batches():
    from sqlalchemy import func, select

    from app.extensions import db
    from app.models import ImportBatch, ImportError, ImportTemplate
    page_number = max(request.args.get("page", 1, type=int), 1)
    statement = (
        select(ImportBatch, ImportTemplate.bank_code, func.count(ImportError.id))
        .join(ImportTemplate, ImportTemplate.id == ImportBatch.template_id)
        .outerjoin(ImportError, ImportError.batch_id == ImportBatch.id)
        .group_by(ImportBatch.id, ImportTemplate.bank_code)
        .order_by(ImportBatch.created_at.desc())
    )
    status = request.args.get("status", "ALL")
    if status != "ALL":
        statement = statement.where(ImportBatch.status == status)
    rows = db.paginate(statement, page=page_number, per_page=15, error_out=False)
    return jsonify(
        items=[{"id": batch.id, "bank_code": bank_code, "status": batch.status,
                "error_rows": error_rows, "created_at": batch.created_at.isoformat(),
                "reverted_at": batch.reverted_at.isoformat() if batch.reverted_at else None}
               for batch, bank_code, error_rows in rows.items],
        total=rows.total, page=rows.page, pages=max(rows.pages, 1))
