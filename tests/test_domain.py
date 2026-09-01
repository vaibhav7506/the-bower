from __future__ import annotations

import sqlite3
from datetime import datetime, timedelta, timezone

import pytest
from sqlalchemy import create_engine, inspect, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app import create_app, initialize_database
from config import sqlite_uri
from extensions import db
from models import (
    ActorType,
    Customer,
    DiningTable,
    OpeningHours,
    Reservation,
    ReservationEvent,
    ReservationEventType,
    ReservationStatus,
    Restaurant,
)


@pytest.fixture()
def database(tmp_path):
    path = tmp_path / "domain.db"
    initialize_database(path)
    engine = create_engine(sqlite_uri(path))
    try:
        yield engine
    finally:
        engine.dispose()


def test_domain_schema_and_seed_data(database) -> None:
    expected_tables = {
        "customers",
        "dining_tables",
        "notification_jobs",
        "opening_hours",
        "reservation_events",
        "reservations",
        "restaurants",
        "special_closures",
        "users",
    }

    assert expected_tables.issubset(set(inspect(database).get_table_names()))
    with Session(database) as session:
        assert session.scalar(select(Restaurant.name)) == "The Bower"
        assert len(session.scalars(select(DiningTable)).all()) == 8
        assert len(session.scalars(select(OpeningHours)).all()) == 12


def test_reservation_keeps_snapshot_and_auditable_history(database) -> None:
    starts_at = datetime(2026, 9, 18, 19, 30, tzinfo=timezone.utc)
    with Session(database) as session:
        table = session.scalar(select(DiningTable).where(DiningTable.display_name == "Table 03"))
        customer = Customer(name="A Guest", email="guest@example.com", phone="+91 90000 00000")
        reservation = Reservation(
            confirmation_code="BWR-7K9M2Q",
            customer=customer,
            table=table,
            customer_name=customer.name,
            email=customer.email,
            phone=customer.phone,
            party_size=4,
            starts_at=starts_at,
            ends_at=starts_at + timedelta(minutes=105),
            status=ReservationStatus.CONFIRMED,
            special_requests="Anniversary table, if possible.",
        )
        reservation.events.append(
            ReservationEvent(
                event_type=ReservationEventType.CREATED,
                actor_type=ActorType.CUSTOMER,
                event_metadata={"source": "website"},
            )
        )
        session.add(reservation)
        session.commit()

        table.active = False
        session.commit()
        session.expire_all()

        saved = session.scalar(
            select(Reservation).where(Reservation.confirmation_code == "BWR-7K9M2Q")
        )
        assert saved is not None
        assert saved.table.display_name == "Table 03"
        assert saved.table.active is False
        assert saved.customer_name == "A Guest"
        assert saved.events[0].event_metadata == {"source": "website"}


def test_database_constraints_reject_invalid_table_capacity(database) -> None:
    with Session(database) as session:
        restaurant_id = session.scalar(select(Restaurant.id))
        session.add(
            DiningTable(
                restaurant_id=restaurant_id,
                display_name="Invalid Table",
                capacity=0,
                section="MAIN_DINING",
                x_position=50,
                y_position=50,
                shape="ROUND",
            )
        )
        with pytest.raises(IntegrityError):
            session.commit()


def test_alembic_upgrade_creates_fresh_schema(tmp_path) -> None:
    database_path = tmp_path / "migration.db"
    app = create_app(
        {
            "TESTING": True,
            "SQLALCHEMY_DATABASE_URI": sqlite_uri(database_path),
        }
    )

    runner = app.test_cli_runner()
    result = runner.invoke(args=["db", "upgrade"])

    assert result.exit_code == 0, result.output
    first_seed = runner.invoke(args=["seed-domain"])
    second_seed = runner.invoke(args=["seed-domain"])
    schema_check = runner.invoke(args=["db", "check"])
    assert first_seed.exit_code == 0, first_seed.output
    assert second_seed.exit_code == 0, second_seed.output
    assert schema_check.exit_code == 0, schema_check.output
    engine = create_engine(sqlite_uri(database_path))
    try:
        assert "alembic_version" in inspect(engine).get_table_names()
        assert "reservation_events" in inspect(engine).get_table_names()
        assert "users" in inspect(engine).get_table_names()
        assert "notification_jobs" in inspect(engine).get_table_names()
        with Session(engine) as session:
            assert len(session.scalars(select(Restaurant)).all()) == 1
            assert len(session.scalars(select(DiningTable)).all()) == 8
    finally:
        engine.dispose()
        with app.app_context():
            db.session.remove()
            db.engine.dispose()


def test_alembic_upgrade_preserves_legacy_form_data(tmp_path) -> None:
    database_path = tmp_path / "legacy.db"
    with sqlite3.connect(database_path) as connection:
        connection.executescript(
            """
            CREATE TABLE newsletter_subscribers (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                email TEXT NOT NULL UNIQUE,
                created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
            );
            CREATE TABLE private_event_inquiries (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                name TEXT NOT NULL,
                email TEXT NOT NULL,
                event_date TEXT NOT NULL,
                party_size INTEGER NOT NULL,
                message TEXT NOT NULL,
                created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
            );
            INSERT INTO newsletter_subscribers (email) VALUES ('existing@example.com');
            """
        )

    app = create_app(
        {
            "TESTING": True,
            "SQLALCHEMY_DATABASE_URI": sqlite_uri(database_path),
        }
    )
    result = app.test_cli_runner().invoke(args=["db", "upgrade"])

    assert result.exit_code == 0, result.output
    with sqlite3.connect(database_path) as connection:
        subscriber_count = connection.execute(
            "SELECT COUNT(*) FROM newsletter_subscribers"
        ).fetchone()[0]
        domain_table = connection.execute(
            "SELECT name FROM sqlite_master WHERE type = 'table' AND name = 'reservations'"
        ).fetchone()

    assert subscriber_count == 1
    assert domain_table == ("reservations",)
    with app.app_context():
        db.session.remove()
        db.engine.dispose()
