from __future__ import annotations

from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo

from app import create_app, initialize_database
from config import sqlite_uri
from extensions import db
from models import User, UserRole


PROJECT_ROOT = Path(__file__).resolve().parents[1]
DATABASE_PATH = PROJECT_ROOT / ".playwright" / "the_bower_e2e.db"
FIXED_NOW = datetime(2026, 9, 1, 10, 0, tzinfo=ZoneInfo("Asia/Kolkata"))


def build_application():
    DATABASE_PATH.parent.mkdir(parents=True, exist_ok=True)
    DATABASE_PATH.unlink(missing_ok=True)
    initialize_database(DATABASE_PATH)
    application = create_app(
        {
            "TESTING": True,
            "SECRET_KEY": "phase-i-browser-tests-only",
            "SQLALCHEMY_DATABASE_URI": sqlite_uri(DATABASE_PATH),
            "RESERVATION_NOW_PROVIDER": lambda timezone_info: FIXED_NOW.astimezone(timezone_info),
            "NOTIFICATION_AUTO_DISPATCH": False,
        }
    )
    with application.app_context():
        admin = User(name="Phase I Admin", email="admin@example.com", role=UserRole.ADMIN)
        admin.set_password("a-secure-admin-password")
        db.session.add(admin)
        db.session.commit()
    return application


if __name__ == "__main__":
    build_application().run(host="127.0.0.1", port=5052, threaded=True, use_reloader=False)
