import io

from flask import Blueprint, abort, jsonify, request, send_file, url_for
from flask_login import current_user, login_required

from app.extensions import db
from app.models import utcnow
from app.services import auth as auth_service
from app.services import profile as profile_service
from app.services.common import ValidationError

from .helpers import json_body, validation_response

profile_bp = Blueprint("profile", __name__, url_prefix="/profile")


def profile_json(user):
    return {
        "id": user.id,
        "email": user.email,
        "full_name": user.full_name,
        "date_of_birth": user.date_of_birth.isoformat(),
        "consent": user.consent,
        "avatar_url": url_for("profile.get_avatar", v=user.avatar_filename) if user.avatar_filename else None,
        "deletion_requested_at": user.deletion_requested_at,
        "role": user.role,
    }


@profile_bp.get("")
@login_required
def get_profile():
    return jsonify(profile_json(current_user))


@profile_bp.patch("")
@login_required
def update_profile():
    data = json_body()
    return validation_response(
        lambda: (
            profile_service.update_profile(current_user, data),
            jsonify(message="Đã cập nhật hồ sơ", profile=profile_json(current_user)),
        )[1]
    )


@profile_bp.get("/avatar")
@login_required
def get_avatar():
    picture = profile_service.avatar_path(current_user)
    if not picture or not picture.is_file():
        abort(404)
    response = send_file(
        io.BytesIO(picture.read_bytes()),
        mimetype=profile_service.avatar_mimetype(current_user),
        download_name=f"avatar{picture.suffix}",
        conditional=True,
    )
    response.cache_control.private = True
    response.cache_control.max_age = 3600
    return response


@profile_bp.post("/avatar")
@login_required
def update_avatar():
    def action():
        profile_service.save_avatar(current_user, request.files.get("avatar"))
        return jsonify(message="Đã cập nhật ảnh đại diện", avatar_url=profile_json(current_user)["avatar_url"])

    return validation_response(action)


@profile_bp.delete("/avatar")
@login_required
def delete_avatar():
    profile_service.remove_avatar(current_user)
    return jsonify(message="Đã xóa ảnh đại diện")


@profile_bp.post("/change-password")
@login_required
def change_password():
    data = json_body()
    def action():
        confirmation = data.get("new_password_confirmation")
        if confirmation is not None and confirmation != data.get("new_password"):
            raise ValidationError("Xác nhận mật khẩu mới không khớp")
        auth_service.change_password(current_user, data.get("current_password"), data.get("new_password"))
        return jsonify(message="Đã đổi mật khẩu")

    return validation_response(action)


@profile_bp.get("/export")
@login_required
def export():
    return send_file(profile_service.export_data(current_user), mimetype="application/zip", as_attachment=True, download_name="smartfinance-export.zip")


@profile_bp.post("/deletion-request")
@login_required
def request_deletion():
    current_user.deletion_requested_at = utcnow()
    db.session.commit()
    return jsonify(message="Yêu cầu xóa tài khoản đã được ghi nhận"), 202
