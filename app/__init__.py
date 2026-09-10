import os
import time

from flask import Flask, g, jsonify, request
from flask_login import current_user

from config import Config

from .errors import register_error_handlers
from .extensions import csrf, db, limiter, login_manager, talisman
from .services import metrics


def create_app(config_object=Config):
    app = Flask(__name__, instance_relative_config=True)
    app.config.from_object(config_object)

    if not app.config.get("TESTING"):
        missing = [key for key in ("SECRET_KEY", "SQLALCHEMY_DATABASE_URI") if not app.config.get(key)]
        if missing:
            raise RuntimeError(
                f"Thiếu cấu hình bắt buộc: {', '.join(missing)}. "
                "Sao chép .env.example thành .env rồi điền SECRET_KEY và DATABASE_URL."
            )

    os.makedirs(app.config["UPLOAD_FOLDER"], exist_ok=True)

    db.init_app(app)
    login_manager.init_app(app)
    limiter.init_app(app)
    csrf.init_app(app)
    talisman.init_app(
        app,
        force_https=app.config["HTTPS_ENABLED"] and not app.testing,
        # Talisman otherwise forces SESSION_COOKIE_SECURE=True on every request
        # (talisman.py::_force_https), overriding config.py. Over the plain-HTTP
        # localhost setup the README documents, a Secure cookie is never sent
        # back by the browser, so session['csrf_token'] is absent on every POST
        # and login is impossible. Bind it to the same switch as force_https.
        session_cookie_secure=app.config["HTTPS_ENABLED"] and not app.testing,
        # NFR-17: no 'unsafe-inline'. The frontend therefore carries no inline
        # <style> blocks and no style="" attributes; widths and ratios are set
        # through the CSSOM (element.style.setProperty), which CSP does not gate.
        content_security_policy={
            "default-src": "'self'",
            "script-src": "'self'",
            "style-src": "'self'",
            "img-src": "'self' data:",
            "base-uri": "'self'",
            "form-action": "'self'",
            "object-src": "'none'",
            "frame-ancestors": "'none'",
        },
        frame_options="DENY",
        referrer_policy="no-referrer",
    )

    from .routes.accounts import accounts_bp
    from .routes.admin import admin_bp
    from .routes.alerts import alerts_bp
    from .routes.auth import auth_bp
    from .routes.budgets import budgets_bp
    from .routes.categories import categories_bp
    from .routes.challenges import challenges_bp
    from .routes.imports import imports_bp
    from .routes.profile import profile_bp
    from .routes.statistics import statistics_bp
    from .routes.support import support_bp
    from .routes.transactions import transactions_bp
    from .routes.ui import ui_bp

    for blueprint in (auth_bp, profile_bp, accounts_bp, categories_bp, transactions_bp, imports_bp, budgets_bp, alerts_bp, challenges_bp, statistics_bp, support_bp, admin_bp, ui_bp):
        app.register_blueprint(blueprint)

    # FR-50: the admin console reports request volume, latency and recent API
    # failures. Both hooks stay off the database so a page load never pays for
    # an extra write; see app/services/metrics.py for the trade-off.
    @app.before_request
    def start_request_timer():
        g.request_started_at = time.perf_counter()

    @app.after_request
    def record_request_metrics(response):
        started = g.pop("request_started_at", None)
        if started is None or request.endpoint == "static":
            return response
        rule = request.url_rule.rule if request.url_rule else request.path
        metrics.record_request(request.method, rule, response.status_code, (time.perf_counter() - started) * 1000)
        if response.status_code >= 400:
            payload = response.get_json(silent=True) if response.is_json else None
            # NFR-10: only the generic message we already returned to the
            # caller is kept, never the request body or a stack trace.
            actor = current_user.id if current_user and current_user.is_authenticated else None
            metrics.record_error(request.method, rule, response.status_code, (payload or {}).get("error", ""), actor)
        return response

    @login_manager.unauthorized_handler
    def unauthorized():
        return jsonify(error="Vui lòng đăng nhập để tiếp tục", status=401), 401

    register_error_handlers(app)

    return app
