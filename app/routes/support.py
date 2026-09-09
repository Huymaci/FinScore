from flask import Blueprint, jsonify, request
from flask_login import current_user, login_required

from app.services import support as service

from .helpers import json_body, validation_response

support_bp = Blueprint("support", __name__, url_prefix="/support-reports")


def support_report_json(report, *, include_user=False):
    payload = {
        "id": report.id,
        "subject": report.subject,
        "message": report.message,
        "status": report.status,
        "created_at": report.created_at.isoformat(),
        "resolved_at": report.resolved_at.isoformat() if report.resolved_at else None,
    }
    if include_user:
        payload["user"] = {
            "id": report.user.id,
            "full_name": report.user.full_name,
            "email": report.user.email,
        }
    return payload


@support_bp.post("")
@login_required
def create_report():
    def action():
        report = service.create_report(current_user.id, json_body())
        return jsonify(support_report_json(report)), 201

    return validation_response(action)


@support_bp.get("")
@login_required
def own_reports():
    page_number = max(request.args.get("page", 1, type=int), 1)
    page = service.list_for_user(current_user.id, page_number, 20)
    return jsonify(
        items=[support_report_json(item) for item in page.items],
        total=page.total,
        page=page.page,
        pages=page.pages,
    )
