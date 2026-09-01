from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime, timedelta, timezone
from zoneinfo import ZoneInfo

from sqlalchemy import select
from sqlalchemy.orm import Session

from models import (
    DiningTable,
    OpeningHours,
    Reservation,
    ReservationStatus,
    Restaurant,
    SpecialClosure,
)


BLOCKING_RESERVATION_STATUSES = (
    ReservationStatus.PENDING,
    ReservationStatus.CONFIRMED,
    ReservationStatus.CHECKED_IN,
)


class UnsupportedPartySize(ValueError):
    pass


@dataclass(frozen=True, slots=True)
class AvailabilitySettings:
    duration_rules: tuple[tuple[int, int], ...] = (
        (2, 90),
        (4, 105),
        (6, 120),
        (8, 135),
    )
    slot_interval_minutes: int = 15
    reset_buffer_minutes: int = 15

    def __post_init__(self) -> None:
        if not self.duration_rules:
            raise ValueError("At least one seating-duration rule is required.")
        maximum_party_sizes = tuple(rule[0] for rule in self.duration_rules)
        if maximum_party_sizes != tuple(sorted(set(maximum_party_sizes))):
            raise ValueError("Seating-duration rules must have unique ascending limits.")
        if any(limit < 1 or minutes < 1 for limit, minutes in self.duration_rules):
            raise ValueError("Seating-duration limits and durations must be positive.")
        if self.slot_interval_minutes < 1:
            raise ValueError("Slot interval must be positive.")
        if self.reset_buffer_minutes < 0:
            raise ValueError("Reset buffer cannot be negative.")
        if any(
            minutes % self.slot_interval_minutes != 0
            for _limit, minutes in self.duration_rules
        ):
            raise ValueError("Seating durations must align with the slot interval.")
        if self.reset_buffer_minutes % self.slot_interval_minutes != 0:
            raise ValueError("Reset buffer must align with the slot interval.")

    def duration_for(self, party_size: int) -> timedelta:
        if party_size < 1:
            raise UnsupportedPartySize("Party size must be at least one guest.")

        for maximum_party_size, duration_minutes in self.duration_rules:
            if party_size <= maximum_party_size:
                return timedelta(minutes=duration_minutes)

        maximum_supported = self.duration_rules[-1][0]
        raise UnsupportedPartySize(
            f"Online reservations support parties of up to {maximum_supported} guests."
        )

    @property
    def reset_buffer(self) -> timedelta:
        return timedelta(minutes=self.reset_buffer_minutes)

    @property
    def slot_interval(self) -> timedelta:
        return timedelta(minutes=self.slot_interval_minutes)


@dataclass(frozen=True, slots=True)
class AvailabilitySlot:
    starts_at: datetime
    ends_at: datetime
    available_tables: tuple[DiningTable, ...]

    @property
    def available_table_ids(self) -> tuple[int, ...]:
        return tuple(table.id for table in self.available_tables)


class AvailabilityService:
    def __init__(
        self,
        session: Session,
        restaurant_id: int,
        settings: AvailabilitySettings | None = None,
    ) -> None:
        self.session = session
        self.restaurant_id = restaurant_id
        self.settings = settings or AvailabilitySettings()
        self.restaurant = session.get(Restaurant, restaurant_id)
        if self.restaurant is None:
            raise LookupError(f"Restaurant {restaurant_id} does not exist.")
        self.timezone = ZoneInfo(self.restaurant.timezone)

    def find_available_slots(
        self,
        service_date: date,
        party_size: int,
    ) -> tuple[AvailabilitySlot, ...]:
        duration = self.settings.duration_for(party_size)
        opening_periods = self._opening_periods(service_date)
        if not opening_periods:
            return ()

        closures = self._closures(service_date)
        if any(closure.full_day for closure in closures):
            return ()

        compatible_tables = self._compatible_tables(party_size)
        if not compatible_tables:
            return ()

        service_window_start = datetime.combine(
            service_date,
            min(period.opens_at for period in opening_periods),
            tzinfo=self.timezone,
        )
        service_window_end = datetime.combine(
            service_date,
            max(period.closes_at for period in opening_periods),
            tzinfo=self.timezone,
        )
        blocking_reservations = self._blocking_reservations(
            compatible_tables,
            service_window_start,
            service_window_end,
        )

        slots: list[AvailabilitySlot] = []
        for opening_period in opening_periods:
            slot_start = datetime.combine(
                service_date,
                opening_period.opens_at,
                tzinfo=self.timezone,
            )
            last_seating = datetime.combine(
                service_date,
                opening_period.last_seating_at,
                tzinfo=self.timezone,
            )
            closes_at = datetime.combine(
                service_date,
                opening_period.closes_at,
                tzinfo=self.timezone,
            )

            while slot_start <= last_seating:
                slot_end = slot_start + duration
                if slot_end <= closes_at and not self._overlaps_closure(
                    slot_start,
                    slot_end,
                    closures,
                ):
                    available_tables = self._remove_reserved_tables(
                        compatible_tables,
                        slot_start,
                        slot_end,
                        blocking_reservations,
                    )
                    if available_tables:
                        slots.append(
                            AvailabilitySlot(
                                starts_at=slot_start,
                                ends_at=slot_end,
                                available_tables=available_tables,
                            )
                        )
                slot_start += self.settings.slot_interval

        return tuple(slots)

    def find_available_tables(
        self,
        starts_at: datetime,
        party_size: int,
    ) -> tuple[DiningTable, ...]:
        local_start, local_end = self.reservation_window(starts_at, party_size)
        if local_start is None or local_end is None:
            return ()

        compatible_tables = self._compatible_tables(party_size)
        blocking_reservations = self._blocking_reservations(
            compatible_tables,
            local_start,
            local_end,
        )
        return self._remove_reserved_tables(
            compatible_tables,
            local_start,
            local_end,
            blocking_reservations,
        )

    def reservation_window(
        self,
        starts_at: datetime,
        party_size: int,
    ) -> tuple[datetime | None, datetime | None]:
        if starts_at.tzinfo is None or starts_at.utcoffset() is None:
            raise ValueError("Reservation times must include a timezone.")

        duration = self.settings.duration_for(party_size)
        local_start = starts_at.astimezone(self.timezone)
        local_end = local_start + duration
        opening_periods = self._opening_periods(local_start.date())
        if not self._fits_opening_period(local_start, local_end, opening_periods):
            return None, None

        closures = self._closures(local_start.date())
        if self._overlaps_closure(local_start, local_end, closures):
            return None, None
        return local_start, local_end

    def _opening_periods(self, service_date: date) -> tuple[OpeningHours, ...]:
        statement = (
            select(OpeningHours)
            .where(
                OpeningHours.restaurant_id == self.restaurant_id,
                OpeningHours.day_of_week == service_date.weekday(),
                OpeningHours.active.is_(True),
            )
            .order_by(OpeningHours.opens_at)
        )
        return tuple(self.session.scalars(statement))

    def _closures(self, service_date: date) -> tuple[SpecialClosure, ...]:
        statement = select(SpecialClosure).where(
            SpecialClosure.restaurant_id == self.restaurant_id,
            SpecialClosure.date == service_date,
        )
        return tuple(self.session.scalars(statement))

    def _compatible_tables(self, party_size: int) -> tuple[DiningTable, ...]:
        statement = (
            select(DiningTable)
            .where(
                DiningTable.restaurant_id == self.restaurant_id,
                DiningTable.active.is_(True),
                DiningTable.capacity >= party_size,
            )
            .order_by(
                DiningTable.capacity,
                DiningTable.accessible,
                DiningTable.display_name,
            )
        )
        return tuple(self.session.scalars(statement))

    def _remove_reserved_tables(
        self,
        compatible_tables: tuple[DiningTable, ...],
        starts_at: datetime,
        ends_at: datetime,
        blocking_reservations: tuple[Reservation, ...],
    ) -> tuple[DiningTable, ...]:
        if not compatible_tables:
            return ()

        starts_utc = starts_at.astimezone(timezone.utc)
        ends_utc = ends_at.astimezone(timezone.utc)
        blocked_table_ids = {
            reservation.dining_table_id
            for reservation in blocking_reservations
            if self._as_utc(reservation.starts_at)
            < ends_utc + self.settings.reset_buffer
            and self._as_utc(reservation.ends_at)
            > starts_utc - self.settings.reset_buffer
        }
        return tuple(
            table for table in compatible_tables if table.id not in blocked_table_ids
        )

    def _blocking_reservations(
        self,
        compatible_tables: tuple[DiningTable, ...],
        starts_at: datetime,
        ends_at: datetime,
    ) -> tuple[Reservation, ...]:
        if not compatible_tables:
            return ()

        table_ids = tuple(table.id for table in compatible_tables)
        starts_utc = starts_at.astimezone(timezone.utc)
        ends_utc = ends_at.astimezone(timezone.utc)
        statement = select(Reservation).where(
            Reservation.dining_table_id.in_(table_ids),
            Reservation.status.in_(BLOCKING_RESERVATION_STATUSES),
            Reservation.starts_at < ends_utc + self.settings.reset_buffer,
            Reservation.ends_at > starts_utc - self.settings.reset_buffer,
        )
        return tuple(self.session.scalars(statement))

    @staticmethod
    def _as_utc(value: datetime) -> datetime:
        if value.tzinfo is None or value.utcoffset() is None:
            return value.replace(tzinfo=timezone.utc)
        return value.astimezone(timezone.utc)

    def _fits_opening_period(
        self,
        starts_at: datetime,
        ends_at: datetime,
        opening_periods: tuple[OpeningHours, ...],
    ) -> bool:
        for opening_period in opening_periods:
            opens_at = datetime.combine(
                starts_at.date(),
                opening_period.opens_at,
                tzinfo=self.timezone,
            )
            last_seating = datetime.combine(
                starts_at.date(),
                opening_period.last_seating_at,
                tzinfo=self.timezone,
            )
            closes_at = datetime.combine(
                starts_at.date(),
                opening_period.closes_at,
                tzinfo=self.timezone,
            )
            offset = starts_at - opens_at
            aligned_to_slot_grid = (
                offset >= timedelta(0)
                and offset % self.settings.slot_interval == timedelta(0)
            )
            if (
                aligned_to_slot_grid
                and starts_at <= last_seating
                and ends_at <= closes_at
            ):
                return True
        return False

    def _overlaps_closure(
        self,
        starts_at: datetime,
        ends_at: datetime,
        closures: tuple[SpecialClosure, ...],
    ) -> bool:
        for closure in closures:
            if closure.full_day:
                return True
            if closure.starts_at is None or closure.ends_at is None:
                continue
            closure_start = datetime.combine(
                closure.date,
                closure.starts_at,
                tzinfo=self.timezone,
            )
            closure_end = datetime.combine(
                closure.date,
                closure.ends_at,
                tzinfo=self.timezone,
            )
            if starts_at < closure_end and ends_at > closure_start:
                return True
        return False
