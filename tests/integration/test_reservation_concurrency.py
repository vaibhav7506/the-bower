from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor
from datetime import datetime
from threading import Barrier
from zoneinfo import ZoneInfo

from sqlalchemy import create_engine, func, select
from sqlalchemy.orm import Session

from app import initialize_database
from config import sqlite_uri
from models import DiningTable, Reservation, ReservationStatus, ReservationTimeBlock, Restaurant
from services import ReservationConflict, ReservationRequest, ReservationService


LOCAL_TIMEZONE = ZoneInfo("Asia/Kolkata")


def test_two_concurrent_requests_cannot_claim_the_same_table(tmp_path) -> None:
    database_path = tmp_path / "concurrency.db"
    initialize_database(database_path)
    engine = create_engine(sqlite_uri(database_path))
    with Session(engine) as lookup_session:
        restaurant_id = lookup_session.scalar(select(Restaurant.id))
        table_id = lookup_session.scalar(
            select(DiningTable.id).where(DiningTable.display_name == "Table 07")
        )

    start_barrier = Barrier(2)

    def attempt_booking(sequence: int):
        request = ReservationRequest(
            starts_at=datetime(2026, 9, 8, 19, 30, tzinfo=LOCAL_TIMEZONE),
            party_size=8,
            customer_name=f"Concurrent Guest {sequence}",
            email=f"concurrent{sequence}@example.com",
            table_id=table_id,
        )
        with Session(engine) as session:
            service = ReservationService(session, restaurant_id)
            start_barrier.wait(timeout=5)
            try:
                reservation = service.create(request)
                return "created", reservation.confirmation_code, ()
            except ReservationConflict as conflict:
                return "conflict", None, conflict.alternatives

    with ThreadPoolExecutor(max_workers=2) as executor:
        results = list(executor.map(attempt_booking, (1, 2)))

    outcomes = sorted(result[0] for result in results)
    assert outcomes == ["conflict", "created"]
    assert any(result[2] for result in results if result[0] == "conflict")

    with Session(engine) as verification_session:
        confirmed_count = verification_session.scalar(
            select(func.count())
            .select_from(Reservation)
            .where(
                Reservation.dining_table_id == table_id,
                Reservation.status == ReservationStatus.CONFIRMED,
            )
        )
        block_count = verification_session.scalar(
            select(func.count()).select_from(ReservationTimeBlock)
        )

    engine.dispose()
    assert confirmed_count == 1
    assert block_count == 10
