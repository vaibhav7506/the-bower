from __future__ import annotations

from datetime import datetime
from zoneinfo import ZoneInfo

import pytest
from sqlalchemy import func, select

from app import create_app, initialize_database
from config import sqlite_uri
from extensions import db
from models import DiningTable, Reservation, ReservationTimeBlock


LOCAL_TIMEZONE = ZoneInfo("Asia/Kolkata")
FIXED_NOW = datetime(2026, 9, 1, 10, 0, tzinfo=LOCAL_TIMEZONE)


@pytest.fixture()
def app(tmp_path):
    database_path = tmp_path / "api.db"
    initialize_database(database_path)
    application = create_app(
        {
            "TESTING": True,
            "SQLALCHEMY_DATABASE_URI": sqlite_uri(database_path),
            "RESERVATION_NOW_PROVIDER": lambda timezone_info: FIXED_NOW.astimezone(
                timezone_info
            ),
        }
    )
    yield application
    with application.app_context():
        db.session.remove()
        db.engine.dispose()


@pytest.fixture()
def client(app):
    return app.test_client()


def reservation_payload(**overrides) -> dict:
    payload = {
        "date": "2026-09-08",
        "time": "19:30",
        "partySize": 4,
        "customer": {
            "name": "A Guest",
            "email": "guest@example.com",
            "phone": "+91 90000 00000",
        },
        "specialRequests": "A quiet corner, if possible.",
    }
    payload.update(overrides)
    return payload


def table_id(app, display_name: str) -> int:
    with app.app_context():
        identifier = db.session.scalar(
            select(DiningTable.id).where(DiningTable.display_name == display_name)
        )
        db.session.rollback()
        return identifier


def test_availability_endpoint_returns_live_slots_and_tables(client) -> None:
    response = client.get("/api/availability?date=2026-09-08&partySize=5")
    payload = response.get_json()

    assert response.status_code == 200
    assert payload["ok"] is True
    assert payload["timezone"] == "Asia/Kolkata"
    assert payload["slots"][0]["time"] == "12:00"
    assert [table["capacity"] for table in payload["slots"][0]["tables"]] == [6, 8]
    assert len(payload["floorPlan"]["tables"]) == 8
    assert payload["floorPlan"]["tables"][0]["shape"] in {
        "ROUND",
        "SQUARE",
        "RECTANGLE",
        "BAR",
    }


@pytest.mark.parametrize(
    ("url", "field"),
    (
        ("/api/availability?date=not-a-date&partySize=2", "date"),
        ("/api/availability?date=2026-09-08&partySize=0", "partySize"),
        ("/api/availability?date=2027-09-08&partySize=2", "date"),
    ),
)
def test_availability_endpoint_validates_query(client, url: str, field: str) -> None:
    response = client.get(url)

    assert response.status_code == 400
    assert response.get_json()["field"] == field


def test_create_and_lookup_reservation(client) -> None:
    created = client.post("/api/reservations", json=reservation_payload())
    reservation = created.get_json()["reservation"]

    assert created.status_code == 201
    assert reservation["confirmationCode"].startswith("BWR-")
    assert len(reservation["confirmationCode"]) == 12
    assert reservation["status"] == "CONFIRMED"
    assert reservation["partySize"] == 4
    assert reservation["table"]["capacity"] == 4

    found = client.get(f"/api/reservations/{reservation['confirmationCode']}")

    assert found.status_code == 200
    assert found.get_json()["reservation"] == reservation


@pytest.mark.parametrize(
    ("changes", "field"),
    (
        ({"partySize": 99}, "partySize"),
        ({"time": "19:37"}, None),
        ({"date": "2026-08-30"}, "date"),
        ({"customer": {"name": "A Guest", "email": "bad"}}, "customer.email"),
        (
            {
                "customer": {
                    "name": "A Guest",
                    "email": "guest@example.com",
                    "phone": "abc",
                }
            },
            "customer.phone",
        ),
    ),
)
def test_create_reservation_validates_browser_data(client, changes: dict, field: str | None) -> None:
    response = client.post("/api/reservations", json=reservation_payload(**changes))
    payload = response.get_json()

    assert response.status_code == 400
    if field is not None:
        assert payload["field"] == field
    assert "traceback" not in str(payload).lower()


def test_conflict_returns_nearby_alternatives(app, client) -> None:
    scarce_table_id = table_id(app, "Table 07")
    first_payload = reservation_payload(partySize=8, tableId=scarce_table_id)
    second_payload = reservation_payload(
        partySize=8,
        tableId=scarce_table_id,
        customer={
            "name": "Another Guest",
            "email": "another@example.com",
            "phone": "+91 91111 11111",
        },
    )

    first = client.post("/api/reservations", json=first_payload)
    second = client.post("/api/reservations", json=second_payload)
    conflict = second.get_json()

    assert first.status_code == 201
    assert second.status_code == 409
    assert conflict["code"] == "RESERVATION_CONFLICT"
    assert "just been reserved" in conflict["message"]
    assert 1 <= len(conflict["alternatives"]) <= 3


def test_create_rejects_a_selected_table_that_is_too_small(app, client) -> None:
    small_table_id = table_id(app, "Table 01")

    response = client.post(
        "/api/reservations",
        json=reservation_payload(partySize=5, tableId=small_table_id),
    )

    assert response.status_code == 400
    assert response.get_json() == {
        "ok": False,
        "code": "INVALID_TABLE",
        "field": "tableId",
        "message": "That table cannot seat the selected party size.",
    }


def test_cancellation_is_verified_idempotent_and_releases_claims(app, client) -> None:
    created = client.post("/api/reservations", json=reservation_payload())
    code = created.get_json()["reservation"]["confirmationCode"]

    denied = client.post(
        f"/api/reservations/{code}/cancel",
        json={"email": "wrong@example.com"},
    )
    cancelled = client.post(
        f"/api/reservations/{code}/cancel",
        json={"email": "guest@example.com"},
    )
    repeated = client.post(
        f"/api/reservations/{code}/cancel",
        json={"email": "guest@example.com"},
    )

    assert denied.status_code == 404
    assert cancelled.status_code == 200
    assert cancelled.get_json()["reservation"]["status"] == "CANCELLED"
    assert repeated.status_code == 200

    with app.app_context():
        reservation_id = db.session.scalar(
            select(Reservation.id).where(Reservation.confirmation_code == code)
        )
        block_count = db.session.scalar(
            select(func.count())
            .select_from(ReservationTimeBlock)
            .where(ReservationTimeBlock.reservation_id == reservation_id)
        )
        db.session.rollback()
    assert block_count == 0


def test_unknown_confirmation_code_is_not_leaky(client) -> None:
    response = client.get("/api/reservations/BWR-22222222")

    assert response.status_code == 404
    assert response.get_json() == {
        "ok": False,
        "code": "RESERVATION_NOT_FOUND",
        "message": "Reservation not found.",
    }
