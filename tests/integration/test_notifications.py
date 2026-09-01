from __future__ import annotations

from datetime import datetime, timedelta, timezone
from zoneinfo import ZoneInfo

import pytest
from sqlalchemy import select

from app import create_app, initialize_database
from config import sqlite_uri
from extensions import db
from models import NotificationJob, NotificationKind, NotificationStatus, Reservation
from services import NotificationService, process_notification_job, render_notification


LOCAL_TIMEZONE = ZoneInfo("Asia/Kolkata")
FIXED_NOW = datetime(2026, 9, 1, 10, 0, tzinfo=LOCAL_TIMEZONE)


@pytest.fixture()
def app(tmp_path):
    database_path = tmp_path / "notifications.db"
    initialize_database(database_path)
    application = create_app(
        {
            "TESTING": True,
            "SQLALCHEMY_DATABASE_URI": sqlite_uri(database_path),
            "RESERVATION_NOW_PROVIDER": lambda timezone_info: FIXED_NOW.astimezone(timezone_info),
            "NOTIFICATION_AUTO_DISPATCH": False,
            "NOTIFICATION_DELIVERY_MODE": "log",
        }
    )
    yield application
    with application.app_context():
        db.session.remove()
        db.engine.dispose()


@pytest.fixture()
def client(app):
    return app.test_client()


def reservation_payload() -> dict:
    return {
        "date": "2026-09-08",
        "time": "19:30",
        "partySize": 4,
        "customer": {"name": "A Guest", "email": "guest@example.com"},
    }


def test_booking_and_cancellation_enqueue_independent_notifications(app, client) -> None:
    created = client.post("/api/reservations", json=reservation_payload())
    code = created.get_json()["reservation"]["confirmationCode"]
    cancelled = client.post(
        f"/api/reservations/{code}/cancel",
        json={"email": "guest@example.com"},
    )

    assert created.status_code == 201
    assert created.get_json()["notification"]["status"] == "PENDING"
    assert cancelled.status_code == 200
    assert cancelled.get_json()["notification"]["status"] == "PENDING"
    with app.app_context():
        jobs = tuple(db.session.scalars(select(NotificationJob).order_by(NotificationJob.id)))
        assert [job.kind for job in jobs] == [
            NotificationKind.BOOKING_CONFIRMATION,
            NotificationKind.CANCELLATION_CONFIRMATION,
        ]


def test_delivery_failure_never_rolls_back_booking_and_can_retry(app, client) -> None:
    created = client.post("/api/reservations", json=reservation_payload())
    code = created.get_json()["reservation"]["confirmationCode"]

    with app.app_context():
        job = db.session.scalar(select(NotificationJob))
        job_id = job.id
        app.config["NOTIFICATION_DELIVERY_MODE"] = "fail"
        first_status = process_notification_job(job_id)
        db.session.expire_all()
        failed_job = db.session.get(NotificationJob, job_id)
        reservation = db.session.scalar(
            select(Reservation).where(Reservation.confirmation_code == code)
        )
        assert first_status == NotificationStatus.RETRY_PENDING
        assert failed_job.attempts == 1
        assert failed_job.last_error == "Delivery provider was unavailable."
        assert reservation.status.value == "CONFIRMED"

        failed_job.run_after = datetime.now(timezone.utc) - timedelta(seconds=1)
        db.session.commit()
        app.config["NOTIFICATION_DELIVERY_MODE"] = "log"
        assert process_notification_job(job_id) == NotificationStatus.SENT


def test_reminder_sweep_is_deduplicated_and_email_contains_management_link(app, client) -> None:
    client.post("/api/reservations", json=reservation_payload())
    reminder_time = datetime(2026, 9, 7, 14, 0, tzinfo=timezone.utc)

    with app.app_context():
        service = NotificationService(db.session)
        first = service.enqueue_due_reminders(reminder_time)
        second = service.enqueue_due_reminders(reminder_time)
        reminder = db.session.get(NotificationJob, first[0])
        rendered = render_notification(reminder)

        assert first == second
        assert reminder.kind == NotificationKind.RESERVATION_REMINDER
        assert "A reminder from The Bower" in rendered.subject
        assert "/api/reservations/BWR-" in rendered.text_body
