"""Uniform JSON error responses for the API surface.

The frontend treats an HTML body as "the API is unreachable" (see
`responseData()` in frontend/app.js), so every error a fetch() call can hit must
carry a JSON body. Without this module a 404 from `owned_or_404()` renders
Flask's default HTML page and the user is told the server is down.

NFR-30: unhandled exceptions return a generic message plus a correlation id;
no stack trace ever reaches the browser.
"""
import logging
import uuid

from flask import jsonify, request
from werkzeug.exceptions import HTTPException

logger = logging.getLogger(__name__)

# Every blueprint that answers fetch() calls rather than serving the SPA shell.
API_PREFIXES = (
    "/auth", "/profile", "/accounts", "/categories", "/transactions",
    "/imports", "/budgets", "/alerts", "/challenges", "/statistics", "/admin",
)

MESSAGES = {
    400: "Yêu cầu không hợp lệ",
    401: "Vui lòng đăng nhập để tiếp tục",
    403: "Bạn không có quyền thực hiện thao tác này",
    404: "Không tìm thấy dữ liệu",
    405: "Phương thức không được hỗ trợ",
    413: "Tệp vượt quá giới hạn 5 MB",
    429: "Bạn thao tác quá nhanh, vui lòng thử lại sau ít phút",
}


def wants_json():
    """True when the caller is the SPA's fetch layer rather than the browser bar."""
    if request.path.startswith(API_PREFIXES):
        return True
    if request.is_json or request.headers.get("X-CSRFToken"):
        return True
    accept = request.accept_mimetypes
    return accept["application/json"] >= accept["text/html"] and accept["application/json"] > 0


def register_error_handlers(app):
    @app.errorhandler(HTTPException)
    def http_error(error):
        if not wants_json():
            return error
        message = MESSAGES.get(error.code, error.description or "Đã xảy ra lỗi")
        return jsonify(error=message, status=error.code), error.code

    @app.errorhandler(Exception)
    def unexpected_error(error):
        # NFR-24: the correlation id is logged, the detail is not echoed back.
        correlation_id = uuid.uuid4().hex[:12]
        logger.exception("Unhandled error correlation_id=%s path=%s", correlation_id, request.path)
        if not wants_json():
            return f"Đã xảy ra lỗi hệ thống. Mã tham chiếu: {correlation_id}", 500
        return jsonify(error="Đã xảy ra lỗi hệ thống, vui lòng thử lại", correlation_id=correlation_id), 500
