import os

from flask import Flask, jsonify

from config import Config

from .errors import register_error_handlers
from .extensions import csrf, db, limiter, login_manager, talisman


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

    @login_manager.unauthorized_handler
    def unauthorized():
        return jsonify(error="Vui lòng đăng nhập để tiếp tục", status=401), 401

    register_error_handlers(app)

    return app
