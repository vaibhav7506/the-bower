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
