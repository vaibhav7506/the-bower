from __future__ import annotations

import re
from datetime import datetime
from zoneinfo import ZoneInfo

import pytest
from sqlalchemy import select

from app import create_app, initialize_database
from config import sqlite_uri
from extensions import db
from models import OpeningHours, Reservation, ReservationEventType, SpecialClosure, User, UserRole


LOCAL_TIMEZONE = ZoneInfo("Asia/Kolkata")
FIXED_NOW = datetime(2026, 9, 1, 10, 0, tzinfo=LOCAL_TIMEZONE)


@pytest.fixture()
def app(tmp_path):
    database_path = tmp_path / "admin.db"
    initialize_database(database_path)
    application = create_app(
        {
            "TESTING": True,
            "SQLALCHEMY_DATABASE_URI": sqlite_uri(database_path),
            "RESERVATION_NOW_PROVIDER": lambda timezone_info: FIXED_NOW.astimezone(timezone_info),
        }
    )
    with application.app_context():
        admin_user = User(name="Admin", email="admin@example.com", role=UserRole.ADMIN)
        admin_user.set_password("a-secure-admin-password")
        staff_user = User(name="Host", email="staff@example.com", role=UserRole.STAFF)
        staff_user.set_password("a-secure-staff-password")
        db.session.add_all((admin_user, staff_user))
        db.session.commit()
    yield application
    with application.app_context():
        db.session.remove()
        db.engine.dispose()


@pytest.fixture()
def client(app):
    return app.test_client()


def csrf_token(client, path: str = "/admin/login") -> str:
    page = client.get(path)
    match = re.search(r'name="csrf_token" value="([^"]+)"', page.get_data(as_text=True))
    assert match is not None
    return match.group(1)


def sign_in(client, email="admin@example.com", password="a-secure-admin-password"):
    return client.post(
        "/admin/login",
        data={"csrf_token": csrf_token(client), "email": email, "password": password},
        follow_redirects=False,
    )


def reservation_payload() -> dict:
    return {
        "date": "2026-09-08",
        "time": "19:30",
        "partySize": 4,
        "customer": {"name": "A Guest", "email": "guest@example.com"},
    }


def test_admin_requires_login_and_successful_login_uses_secure_session_settings(app, client) -> None:
    protected = client.get("/admin")
    signed_in = sign_in(client)

    assert protected.status_code == 302
    assert "/admin/login" in protected.headers["Location"]
    assert signed_in.status_code == 302
    assert signed_in.headers["Location"].endswith("/admin")
    cookie = "\n".join(signed_in.headers.getlist("Set-Cookie"))
    assert "HttpOnly" in cookie
    assert "SameSite=Lax" in cookie
    with app.app_context():
        user = db.session.scalar(select(User).where(User.email == "admin@example.com"))
        assert user.password_hash != "a-secure-admin-password"
        assert user.last_login_at is not None


def test_login_lockout_after_repeated_failures(app, client) -> None:
    for _attempt in range(5):
        response = sign_in(client, password="incorrect-password")
        assert response.status_code == 200

    blocked = sign_in(client)
    assert "Too many sign-in attempts" in blocked.get_data(as_text=True)
    with app.app_context():
        user = db.session.scalar(select(User).where(User.email == "admin@example.com"))
        assert user.locked_until is not None


def test_csrf_and_role_authorization_are_enforced(client) -> None:
    sign_in(client, email="staff@example.com", password="a-secure-staff-password")

    assert client.get("/admin/tables").status_code == 403
    assert client.post("/admin/logout", data={}).status_code == 400


def test_admin_reservation_lifecycle_is_audited(app, client) -> None:
    created = client.post("/api/reservations", json=reservation_payload())
    code = created.get_json()["reservation"]["confirmationCode"]
    sign_in(client)
    detail = client.get(f"/admin/reservations/{code}")
    token = csrf_token(client, f"/admin/reservations/{code}")
    checked_in = client.post(
        f"/admin/reservations/{code}/status",
        data={"csrf_token": token, "status": "CHECKED_IN"},
    )

    assert detail.status_code == 200
    assert "A Guest" in detail.get_data(as_text=True)
    assert checked_in.status_code == 302
    with app.app_context():
        reservation = db.session.scalar(
            select(Reservation).where(Reservation.confirmation_code == code)
        )
        assert reservation.status.value == "CHECKED_IN"
        assert reservation.events[-1].event_type == ReservationEventType.CHECKED_IN
        assert reservation.events[-1].actor_reference == "admin@example.com"


def test_admin_can_change_hours_and_add_closure(app, client) -> None:
    sign_in(client)
    with app.app_context():
        period_id = db.session.scalar(select(OpeningHours.id).order_by(OpeningHours.id))
    hours_token = csrf_token(client, "/admin/hours")
    updated = client.post(
        "/admin/hours",
        data={
            "csrf_token": hours_token,
            "period_id": period_id,
            "opens_at": "12:00",
            "last_seating_at": "13:15",
            "closes_at": "15:00",
            "active": "on",
        },
    )
    closure_token = csrf_token(client, "/admin/closures")
    closure = client.post(
        "/admin/closures",
        data={
            "csrf_token": closure_token,
            "date": "2026-09-22",
            "reason": "Private celebration",
            "full_day": "on",
        },
    )

    assert updated.status_code == 302
    assert closure.status_code == 302
    with app.app_context():
        period = db.session.get(OpeningHours, period_id)
        assert period.last_seating_at.strftime("%H:%M") == "13:15"
        assert db.session.scalar(
            select(SpecialClosure.reason).where(SpecialClosure.date == datetime(2026, 9, 22).date())
        ) == "Private celebration"
