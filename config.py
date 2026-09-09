import os
from datetime import timedelta

from dotenv import load_dotenv

load_dotenv()


class Config:
    SECRET_KEY = os.getenv("SECRET_KEY")
    SQLALCHEMY_DATABASE_URI = os.getenv("DATABASE_URL")
    SQLALCHEMY_ENGINE_OPTIONS = {"pool_pre_ping": True, "pool_recycle": 280}
    SQLALCHEMY_TRACK_MODIFICATIONS = False
    MAX_CONTENT_LENGTH = 5 * 1024 * 1024
    PERMANENT_SESSION_LIFETIME = timedelta(minutes=30)
    SESSION_COOKIE_HTTPONLY = True
    HTTPS_ENABLED = os.getenv("HTTPS_ENABLED", "false").lower() == "true"
    SESSION_COOKIE_SECURE = HTTPS_ENABLED
    SESSION_COOKIE_SAMESITE = "Lax"
    WTF_CSRF_ENABLED = True
    UPLOAD_FOLDER = os.getenv("UPLOAD_FOLDER", os.path.join(os.getcwd(), "instance", "uploads"))
    # Flask-Limiter keeps its counters here. The default in-process store is
    # per-worker: under `gunicorn -w 4` the auth limits the README relies on
    # (10/min on login and register) effectively multiply by the worker count
    # and reset on every reload. Point this at Redis/Memcached in production so
    # the limit is shared. Setting it explicitly also silences the library's
    # "in-memory storage is not recommended" startup warning.
    RATELIMIT_STORAGE_URI = os.getenv("RATELIMIT_STORAGE_URI", "memory://")


class TestConfig(Config):
    TESTING = True
    SECRET_KEY = "unit-test-only"
    SQLALCHEMY_DATABASE_URI = "sqlite:///:memory:"
    SQLALCHEMY_ENGINE_OPTIONS = {}
    WTF_CSRF_ENABLED = False
    SESSION_COOKIE_SECURE = False
    # Pin the store so a developer's real RATELIMIT_STORAGE_URI never leaks into
    # the test run.
    RATELIMIT_STORAGE_URI = "memory://"
