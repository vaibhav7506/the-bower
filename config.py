from __future__ import annotations

import os
from datetime import timedelta
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parent


def sqlite_uri(database_path: Path) -> str:
    return f"sqlite:///{database_path.resolve().as_posix()}"


def database_uri() -> str:
    configured_uri = os.environ.get("DATABASE_URL")
    if configured_uri:
        return configured_uri.replace("postgres://", "postgresql://", 1)

    database_path = Path(
        os.environ.get(
            "DATABASE_PATH",
            str(PROJECT_ROOT / "instance" / "the_bower.db"),
        )
    )
    return sqlite_uri(database_path)


class Config:
    SECRET_KEY = os.environ.get(
        "SECRET_KEY",
        "development-only-change-before-production",
    )
    SQLALCHEMY_DATABASE_URI = database_uri()
    SQLALCHEMY_TRACK_MODIFICATIONS = False
    SQLALCHEMY_ENGINE_OPTIONS = {"pool_pre_ping": True}
    RESERVATION_BOOKING_HORIZON_DAYS = 90
    RESERVATION_MINIMUM_NOTICE_MINUTES = 30
    NOTIFICATION_AUTO_DISPATCH = True
    NOTIFICATION_DELIVERY_MODE = os.environ.get("NOTIFICATION_DELIVERY_MODE", "log")
    NOTIFICATION_MAX_ATTEMPTS = 5
    NOTIFICATION_FROM_EMAIL = os.environ.get("NOTIFICATION_FROM_EMAIL", "tables@thebower.example")
    SMTP_HOST = os.environ.get("SMTP_HOST")
    SMTP_PORT = int(os.environ.get("SMTP_PORT", "587"))
    SMTP_USERNAME = os.environ.get("SMTP_USERNAME")
    SMTP_PASSWORD = os.environ.get("SMTP_PASSWORD")
    SMTP_STARTTLS = os.environ.get("SMTP_STARTTLS", "true").lower() != "false"
    PERMANENT_SESSION_LIFETIME = timedelta(hours=8)
    SESSION_COOKIE_HTTPONLY = True
    SESSION_COOKIE_SAMESITE = "Lax"
    SESSION_COOKIE_SECURE = os.environ.get("FLASK_ENV") == "production" or bool(
        os.environ.get("RENDER")
    )
    PUBLIC_BASE_URL = (
        os.environ.get("PUBLIC_BASE_URL")
        or os.environ.get("RENDER_EXTERNAL_URL")
        or "http://127.0.0.1:5000"
    ).rstrip("/")
    SEND_FILE_MAX_AGE_DEFAULT = timedelta(days=30)
    COMPRESS_MIMETYPES = (
        "text/html",
        "text/css",
        "application/javascript",
        "application/json",
        "image/svg+xml",
    )
