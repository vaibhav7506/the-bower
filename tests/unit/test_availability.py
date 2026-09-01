from __future__ import annotations

from datetime import date, datetime, timedelta, timezone
from itertools import count
from zoneinfo import ZoneInfo

import pytest
from sqlalchemy import create_engine, select
from sqlalchemy.orm import Session

from app import initialize_database
from config import sqlite_uri
from models import (
    Customer,
    DiningTable,
    Reservation,
    ReservationStatus,
    Restaurant,
    SpecialClosure,
)
from services import AvailabilityService, AvailabilitySettings, UnsupportedPartySize


LOCAL_TIMEZONE = ZoneInfo("Asia/Kolkata")
OPEN_TUESDAY = date(2026, 9, 8)
CLOSED_MONDAY = date(2026, 9, 7)
confirmation_sequence = count(1)


@pytest.fixture()
def session(tmp_path):
    database_path = tmp_path / "availability.db"
    initialize_database(database_path)
    engine = create_engine(sqlite_uri(database_path))
    with Session(engine) as database_session:
        yield database_session
    engine.dispose()


@pytest.fixture()
def availability(session) -> AvailabilityService:
    restaurant_id = session.scalar(select(Restaurant.id))
    return AvailabilityService(session, restaurant_id)


def local_datetime(hour: int, minute: int = 0) -> datetime:
    return datetime(2026, 9, 8, hour, minute, tzinfo=LOCAL_TIMEZONE)


def add_reservation(
    session: Session,
    table_name: str,
    starts_at: datetime,
    ends_at: datetime,
    status: ReservationStatus = ReservationStatus.CONFIRMED,
) -> Reservation:
    sequence = next(confirmation_sequence)
    table = session.scalar(
        select(DiningTable).where(DiningTable.display_name == table_name)
    )
    customer = Customer(
        name=f"Guest {sequence}",
        email=f"guest{sequence}@example.com",
    )
    reservation = Reservation(
        confirmation_code=f"BWR-T{sequence:05d}",
        customer=customer,
        table=table,
        customer_name=customer.name,
        email=customer.email,
        party_size=min(table.capacity, 4),
        starts_at=starts_at.astimezone(timezone.utc),
        ends_at=ends_at.astimezone(timezone.utc),
        status=status,
    )
    session.add(reservation)
    session.commit()
    return reservation


def test_closed_day_has_no_slots(availability) -> None:
    assert availability.find_available_slots(CLOSED_MONDAY, party_size=2) == ()


def test_slots_respect_duration_and_last_seating(availability) -> None:
    two_guest_slots = availability.find_available_slots(OPEN_TUESDAY, party_size=2)
    six_guest_slots = availability.find_available_slots(OPEN_TUESDAY, party_size=6)

    assert two_guest_slots[0].starts_at.hour == 12
    assert two_guest_slots[-1].starts_at.time().isoformat() == "21:30:00"
    assert two_guest_slots[-1].ends_at.time().isoformat() == "23:00:00"
    assert six_guest_slots[-1].starts_at.time().isoformat() == "21:00:00"
    assert six_guest_slots[-1].ends_at.time().isoformat() == "23:00:00"


def test_table_capacity_is_respected_and_best_fit_is_first(availability) -> None:
    tables = availability.find_available_tables(local_datetime(19, 30), party_size=5)

    assert [(table.display_name, table.capacity) for table in tables] == [
        ("Table 06", 6),
        ("Table 07", 8),
    ]


def test_off_grid_and_after_hours_requests_are_rejected(availability) -> None:
    assert availability.find_available_tables(local_datetime(19, 37), party_size=2) == ()
    assert availability.find_available_tables(local_datetime(11, 0), party_size=2) == ()


def test_active_reservation_removes_occupied_table(session, availability) -> None:
    add_reservation(
        session,
        "Table 03",
        local_datetime(19, 30),
        local_datetime(21, 15),
    )

    tables = availability.find_available_tables(local_datetime(19, 30), party_size=4)

    assert "Table 03" not in {table.display_name for table in tables}
    assert "Table 04" in {table.display_name for table in tables}


def test_reset_buffer_is_respected(session, availability) -> None:
    add_reservation(
        session,
        "Table 03",
        local_datetime(18, 0),
        local_datetime(19, 20),
    )

    tables = availability.find_available_tables(local_datetime(19, 30), party_size=4)

    assert "Table 03" not in {table.display_name for table in tables}


def test_table_is_available_at_exact_buffer_boundary(session, availability) -> None:
    add_reservation(
        session,
        "Table 03",
        local_datetime(18, 0),
        local_datetime(19, 15),
    )

    tables = availability.find_available_tables(local_datetime(19, 30), party_size=4)

    assert "Table 03" in {table.display_name for table in tables}


def test_cancelled_reservation_does_not_block_table(session, availability) -> None:
    add_reservation(
        session,
        "Table 03",
        local_datetime(19, 30),
        local_datetime(21, 15),
        status=ReservationStatus.CANCELLED,
    )

    tables = availability.find_available_tables(local_datetime(19, 30), party_size=4)

    assert "Table 03" in {table.display_name for table in tables}


def test_inactive_table_is_never_offered(session, availability) -> None:
    table = session.scalar(
        select(DiningTable).where(DiningTable.display_name == "Table 07")
    )
    table.active = False
    session.commit()

    assert availability.find_available_tables(local_datetime(19, 30), party_size=8) == ()


def test_full_day_special_closure_removes_all_availability(
    session,
    availability,
) -> None:
    session.add(
        SpecialClosure(
            restaurant_id=availability.restaurant_id,
            date=OPEN_TUESDAY,
            reason="Private event",
            full_day=True,
        )
    )
    session.commit()

    assert availability.find_available_slots(OPEN_TUESDAY, party_size=2) == ()
    assert availability.find_available_tables(local_datetime(19, 30), party_size=2) == ()


def test_partial_closure_only_removes_overlapping_slots(session, availability) -> None:
    session.add(
        SpecialClosure(
            restaurant_id=availability.restaurant_id,
            date=OPEN_TUESDAY,
            reason="Private drinks reception",
            full_day=False,
            starts_at=local_datetime(18, 30).time(),
            ends_at=local_datetime(20, 0).time(),
        )
    )
    session.commit()

    assert availability.find_available_tables(local_datetime(18, 0), party_size=2) == ()
    assert availability.find_available_tables(local_datetime(20, 0), party_size=2)


def test_scarce_table_removes_conflicting_slot(session, availability) -> None:
    add_reservation(
        session,
        "Table 07",
        local_datetime(19, 30),
        local_datetime(21, 45),
    )

    slots = availability.find_available_slots(OPEN_TUESDAY, party_size=8)
    slot_times = {slot.starts_at.strftime("%H:%M") for slot in slots}

    assert "19:30" not in slot_times
    assert "12:00" in slot_times


def test_settings_are_centralized_and_configurable() -> None:
    settings = AvailabilitySettings(
        duration_rules=((2, 75), (4, 90)),
        slot_interval_minutes=30,
        reset_buffer_minutes=20,
    )

    assert settings.duration_for(2) == timedelta(minutes=75)
    assert settings.slot_interval == timedelta(minutes=30)
    assert settings.reset_buffer == timedelta(minutes=20)
    with pytest.raises(UnsupportedPartySize):
        settings.duration_for(5)
    with pytest.raises(ValueError, match="Slot interval"):
        AvailabilitySettings(slot_interval_minutes=0)
    with pytest.raises(ValueError, match="ascending"):
        AvailabilitySettings(duration_rules=((4, 90), (2, 75)))


def test_invalid_party_size_and_naive_time_are_rejected(availability) -> None:
    with pytest.raises(UnsupportedPartySize):
        availability.find_available_slots(OPEN_TUESDAY, party_size=0)
    with pytest.raises(ValueError, match="timezone"):
        availability.find_available_tables(
            datetime(2026, 9, 8, 19, 30),
            party_size=2,
        )
