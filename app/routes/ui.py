from pathlib import Path

from flask import Blueprint, abort, send_from_directory

FRONTEND_DIR = Path(__file__).resolve().parents[2] / "frontend"
# Only genuine static assets are reachable. send_from_directory already blocks
# path traversal; this stops the catch-all from also serving frontend/README.md
# or any stray script/dotfile that lands in the folder.
SERVABLE_SUFFIXES = {".html", ".js", ".css", ".json", ".png", ".svg", ".ico", ".webmanifest", ".woff", ".woff2", ".map"}
ui_bp = Blueprint("ui", __name__)


def _no_stale(response):
    # The frontend is a single un-hashed bundle (styles.css / app.js / index.html).
    # Without this, browsers hold a stale copy for hours after a deploy and the UI
    # looks broken. "no-cache" still allows a cheap 304 via ETag/Last-Modified.
    response.headers["Cache-Control"] = "no-cache"
    return response


@ui_bp.get("/")
def index():
    return _no_stale(send_from_directory(FRONTEND_DIR, "index.html"))


@ui_bp.get("/<path:filename>")
def assets(filename):
    if Path(filename).suffix.lower() not in SERVABLE_SUFFIXES:
        abort(404)
    return _no_stale(send_from_directory(FRONTEND_DIR, filename))
