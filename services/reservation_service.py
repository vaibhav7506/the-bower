from __future__ import annotations

import secrets
import time
from dataclasses import dataclass
from datetime import datetime, timezone

from sqlalchemy import select, text
from sqlalchemy.exc import IntegrityError, OperationalError
from sqlalchemy.orm import Session, selectinload

from models import (
    ActorType,
    Customer,
    DiningTable,
    Reservation,
    ReservationEvent,
    ReservationEventType,
    ReservationStatus,
    ReservationTimeBlock,
)
from .availability import AvailabilityService, AvailabilitySettings, AvailabilitySlot


CONFIRMATION_ALPHABET = "23456789ABCDEFGHJKLMNPQRSTUVWXYZ"


@dataclass(frozen=True, slots=True)
class ReservationRequest:
    starts_at: datetime
    party_size: int
    customer_name: str
    email: str
    phone: str | None = None
    special_requests: str | None = None
    table_id: int | None = None


class ReservationConflict(Exception):
    def __init__(
        self,
        alternatives: tuple[AvailabilitySlot, ...],
        message: str = "That table has just been reserved.",
    ) -> None:
        super().__init__(message)
        self.alternatives = alternatives


class ReservationNotFound(LookupError):
    pass


class ReservationStateError(ValueError):
    pass


class ReservationEligibilityError(ValueError):
    def __init__(
        self,
        message: str,
        code: str = "INVALID_RESERVATION_TIME",
        field: str = "time",
    ) -> None:
        super().__init__(message)
        self.code = code
        self.field = field


class _TableUnavailable(Exception):
    pass


class ReservationService:
    def __init__(
        self,
        session: Session,
        restaurant_id: int,
        availability_settings: AvailabilitySettings | None = None,
    ) -> None:
        self.session = session
        self.restaurant_id = restaurant_id
        self.availability_settings = availability_settings or AvailabilitySettings()

    def create(self, request: ReservationRequest) -> Reservation:
        if request.starts_at.tzinfo is None or request.starts_at.utcoffset() is None:
            raise ValueError("Reservation times must include a timezone.")
        if self.session.in_transaction():
            raise RuntimeError("Reservation creation requires a clean database session.")

        for attempt in range(3):
            try:
                self._begin_write_transaction()
                reservation = self._create_inside_transaction(request)
                self.session.commit()
                return reservation
            except _TableUnavailable:
                self.session.rollback()
                raise self._conflict_for(request) from None
            except IntegrityError:
                self.session.rollback()
                raise self._conflict_for(request) from None
            except OperationalError as error:
                self.session.rollback()
                if not self._is_retryable_lock(error) or attempt == 2:
                    raise
                time.sleep(0.05 * (2**attempt))
            except Exception:
                self.session.rollback()
                raise

        raise RuntimeError("Reservation transaction retry limit was exhausted.")

    def get_by_confirmation_code(self, confirmation_code: str) -> Reservation:
        statement = (
            select(Reservation)
            .options(
                selectinload(Reservation.table),
                selectinload(Reservation.events),
            )
            .where(Reservation.confirmation_code == confirmation_code.upper())
        )
        reservation = self.session.scalar(statement)
        if reservation is None:
            raise ReservationNotFound("Reservation not found.")
        return reservation

    def cancel(self, confirmation_code: str, email: str) -> Reservation:
        if self.session.in_transaction():
            raise RuntimeError("Reservation cancellation requires a clean database session.")

        try:
            self._begin_write_transaction()
            statement = (
                select(Reservation)
                .options(selectinload(Reservation.time_blocks))
                .where(Reservation.confirmation_code == confirmation_code.upper())
            )
            if self.session.get_bind().dialect.name != "sqlite":
                statement = statement.with_for_update()
            reservation = self.session.scalar(statement)
            if reservation is None or reservation.email.lower() != email.lower():
                raise ReservationNotFound("Reservation not found.")
            if reservation.status == ReservationStatus.CANCELLED:
                self.session.commit()
                return reservation
            if reservation.status not in {
                ReservationStatus.PENDING,
                ReservationStatus.CONFIRMED,
            }:
                raise ReservationStateError(
                    "This reservation can no longer be cancelled online."
                )

            reservation.status = ReservationStatus.CANCELLED
            reservation.time_blocks.clear()
            reservation.events.append(
                ReservationEvent(
                    event_type=ReservationEventType.CANCELLED,
                    actor_type=ActorType.CUSTOMER,
                    event_metadata={"channel": "website"},
                )
            )
            self.session.commit()
            return reservation
        except Exception:
            self.session.rollback()
            raise

    def _create_inside_transaction(
        self,
        request: ReservationRequest,
    ) -> Reservation:
        self._lock_candidate_tables(request.party_size)
        availability = AvailabilityService(
            self.session,
            self.restaurant_id,
            self.availability_settings,
        )
        local_start, local_end = availability.reservation_window(
            request.starts_at,
            request.party_size,
        )
        if local_start is None or local_end is None:
            raise ReservationEligibilityError(
                "That time is outside the restaurant's available seating periods."
            )

        if request.table_id is not None:
            requested_table = self.session.get(DiningTable, request.table_id)
            if (
                requested_table is None
                or requested_table.restaurant_id != self.restaurant_id
                or not requested_table.active
            ):
                raise ReservationEligibilityError(
                    "Choose an available dining table.",
                    code="INVALID_TABLE",
                    field="tableId",
                )
            if requested_table.capacity < request.party_size:
                raise ReservationEligibilityError(
                    "That table cannot seat the selected party size.",
                    code="INVALID_TABLE",
                    field="tableId",
                )

        available_tables = availability.find_available_tables(
            request.starts_at,
            request.party_size,
        )
        if request.table_id is not None:
            selected_table = next(
                (table for table in available_tables if table.id == request.table_id),
                None,
            )
        else:
            selected_table = available_tables[0] if available_tables else None
        if selected_table is None:
            raise _TableUnavailable

        ends_at = local_end
        customer = Customer(
            name=request.customer_name,
            email=request.email,
            phone=request.phone,
        )
        reservation = Reservation(
            confirmation_code=self._confirmation_code(),
            customer=customer,
            table=selected_table,
            customer_name=request.customer_name,
            email=request.email,
            phone=request.phone,
            party_size=request.party_size,
            starts_at=request.starts_at.astimezone(timezone.utc),
            ends_at=ends_at.astimezone(timezone.utc),
            status=ReservationStatus.CONFIRMED,
            special_requests=request.special_requests,
        )
        reservation.events.extend(
            (
                ReservationEvent(
                    event_type=ReservationEventType.CREATED,
                    actor_type=ActorType.CUSTOMER,
                    event_metadata={"channel": "website"},
                ),
                ReservationEvent(
                    event_type=ReservationEventType.CONFIRMED,
                    actor_type=ActorType.SYSTEM,
                    event_metadata={"table": selected_table.display_name},
                ),
            )
        )
        self.session.add(reservation)
        self.session.flush()

        block_start = request.starts_at.astimezone(timezone.utc)
        claim_end = ends_at.astimezone(timezone.utc) + self.availability_settings.reset_buffer
        while block_start < claim_end:
            reservation.time_blocks.append(
                ReservationTimeBlock(
                    dining_table_id=selected_table.id,
                    starts_at=block_start,
                )
            )
            block_start += self.availability_settings.slot_interval
        self.session.flush()
        return reservation

    def _begin_write_transaction(self) -> None:
        if self.session.get_bind().dialect.name == "sqlite":
            self.session.execute(text("BEGIN IMMEDIATE"))
        else:
            self.session.begin()

    def _lock_candidate_tables(self, party_size: int) -> None:
        if self.session.get_bind().dialect.name == "sqlite":
            return
        statement = (
            select(DiningTable.id)
            .where(
                DiningTable.restaurant_id == self.restaurant_id,
                DiningTable.active.is_(True),
                DiningTable.capacity >= party_size,
            )
            .with_for_update()
        )
        tuple(self.session.scalars(statement))

    def _conflict_for(self, request: ReservationRequest) -> ReservationConflict:
        availability = AvailabilityService(
            self.session,
            self.restaurant_id,
            self.availability_settings,
        )
        slots = availability.find_available_slots(
            request.starts_at.astimezone(availability.timezone).date(),
            request.party_size,
        )
        requested_utc = request.starts_at.astimezone(timezone.utc)
        alternatives = tuple(
            sorted(
                (slot for slot in slots if slot.starts_at != request.starts_at),
                key=lambda slot: abs(
                    (slot.starts_at.astimezone(timezone.utc) - requested_utc).total_seconds()
                ),
            )[:3]
        )
        self.session.rollback()
        return ReservationConflict(alternatives)

    @staticmethod
    def _confirmation_code() -> str:
        suffix = "".join(secrets.choice(CONFIRMATION_ALPHABET) for _ in range(8))
        return f"BWR-{suffix}"

    @staticmethod
    def _is_retryable_lock(error: OperationalError) -> bool:
        return "locked" in str(error).lower() or "busy" in str(error).lower()
