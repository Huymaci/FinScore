from flask import Blueprint, jsonify, request, send_file
from flask_login import current_user, login_required

from app.extensions import db
from app.models import ImportTemplate
from app.services.imports import (
    cancel_preview,
    clear_import_history,
    confirm,
    delete_import_history,
    delete_imported_transactions,
    error_csv,
    import_history,
    preview,
    preview_page,
)

from .helpers import json_body, validation_response

imports_bp = Blueprint("imports", __name__, url_prefix="/imports")


@imports_bp.get("/templates")
@login_required
def list_templates():
    items = db.session.query(ImportTemplate).filter_by(active=True).order_by(ImportTemplate.bank_code, ImportTemplate.name).all()
    return jsonify(items=[{"id": item.id, "bank_code": item.bank_code, "name": item.name} for item in items])


@imports_bp.post("/preview")
@login_required
def preview_import():
    def action():
        uploaded = request.files.get("file")
        if not uploaded:
            from app.services.common import ValidationError
            raise ValidationError("Thiếu tệp sao kê")
        summary = preview(current_user, int(request.form.get("account_id", 0)), request.form.get("template_id", type=int), uploaded)
        return jsonify(summary), 201
    return validation_response(action)


@imports_bp.get("/history")
@login_required
def history_imports():
    return jsonify(items=import_history(current_user))


def _remove_transactions_requested():
    """The caller states explicitly whether the transactions an import created
    go with the history entry; anything else keeps them."""
    return request.args.get("remove_transactions", "").lower() in {"1", "true", "yes"}


def _selected_batch_ids():
    """An optional ?ids=1,2,3 narrows the delete to the entries the user ticked;
    without it the whole history goes."""
    raw = request.args.get("ids")
    if raw is None:
        return None
    return [int(value) for value in raw.split(",") if value.strip().isdigit()]


@imports_bp.delete("/history")
@login_required
def clear_history_imports():
    return validation_response(lambda: jsonify(clear_import_history(
        current_user,
        _remove_transactions_requested(),
        _selected_batch_ids(),
    )))


@imports_bp.delete("/<int:batch_id>/history")
@login_required
def delete_history_import(batch_id):
    return validation_response(lambda: jsonify(
        delete_import_history(current_user, batch_id, _remove_transactions_requested()),
    ))


@imports_bp.get("/<int:batch_id>/preview")
@login_required
def get_preview_page(batch_id):
    return validation_response(lambda: jsonify(preview_page(
        current_user,
        batch_id,
        request.args.get("page", 1, type=int),
        request.args.get("per_page", 25, type=int),
    )))


@imports_bp.post("/<int:batch_id>/confirm")
@login_required
def confirm_import(batch_id):
    data = json_body()
    return validation_response(lambda: (jsonify(imported=confirm(
        current_user,
        batch_id,
        data.get("decisions"),
        data.get("category_overrides"),
        data.get("notes"),
    )), 201))


@imports_bp.delete("/<int:batch_id>/preview")
@login_required
def cancel_preview_import(batch_id):
    def action():
        cancel_preview(current_user, batch_id)
        return "", 204
    return validation_response(action)


@imports_bp.delete("/<int:batch_id>/transactions")
@login_required
def delete_import_transactions(batch_id):
    return validation_response(lambda: jsonify(removed=delete_imported_transactions(current_user, batch_id)))


@imports_bp.get("/<int:batch_id>/errors.csv")
@login_required
def download_errors(batch_id):
    return send_file(error_csv(current_user, batch_id), mimetype="text/csv", as_attachment=True, download_name=f"import-{batch_id}-errors.csv")
