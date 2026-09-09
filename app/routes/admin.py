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
