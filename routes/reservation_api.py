from __future__ import annotations

import re
from datetime import date, datetime, time, timedelta, timezone
from zoneinfo import ZoneInfo

from flask import Blueprint, current_app, jsonify, request
from sqlalchemy import select
from sqlalchemy.exc import OperationalError
from sqlalchemy.orm import Session

from extensions import db
from models import Reservation, Restaurant
from services import (
    AvailabilityService,
    ReservationConflict,
    ReservationEligibilityError,
    ReservationNotFound,
    ReservationRequest,
    ReservationService,
    ReservationStateError,
    UnsupportedPartySize,
)


reservation_api = Blueprint("reservation_api", __name__)
EMAIL_PATTERN = re.compile(r"^[^\s@]+@[^\s@]+\.[^\s@]+$")
PHONE_PATTERN = re.compile(r"^\+?[0-9][0-9\s().-]{6,30}$")
CONFIRMATION_PATTERN = re.compile(r"^BWR-[23456789ABCDEFGHJKLMNPQRSTUVWXYZ]{8}$")


@reservation_api.get("/api/availability")
def availability():
    service_date = _parse_date(request.args.get("date"))
    party_size = _parse_party_size(request.args.get("partySize"))
    if service_date is None:
        return _error("Choose a valid reservation date.", 400, "INVALID_DATE", "date")
    if party_size is None:
        return _error(
            "Choose a supported party size.",
            400,
            "INVALID_PARTY_SIZE",
            "partySize",
        )

    restaurant = db.session.scalar(
        select(Restaurant).where(Restaurant.name == "The Bower")
    )
    if restaurant is None:
        return _error(
            "Reservations are temporarily unavailable.",
            503,
            "RESERVATIONS_UNAVAILABLE",
        )

    timezone_info = ZoneInfo(restaurant.timezone)
    now = _now(timezone_info)
    eligibility_error = _validate_date_window(service_date, now)
    if eligibility_error is not None:
        return eligibility_error

    service = AvailabilityService(db.session, restaurant.id)
    try:
        slots = service.find_available_slots(service_date, party_size)
    except UnsupportedPartySize as error:
        return _error(str(error), 400, "INVALID_PARTY_SIZE", "partySize")

    minimum_start = now + timedelta(
        minutes=current_app.config["RESERVATION_MINIMUM_NOTICE_MINUTES"]
    )
    visible_slots = tuple(slot for slot in slots if slot.starts_at >= minimum_start)
    return jsonify(
        ok=True,
        date=service_date.isoformat(),
        partySize=party_size,
        timezone=restaurant.timezone,
        slots=[_slot_payload(slot) for slot in visible_slots],
    )


@reservation_api.post("/api/reservations")
def create_reservation():
    payload = request.get_json(silent=True)
    if not isinstance(payload, dict):
        return _error("Send reservation details as JSON.", 400, "INVALID_REQUEST")

    restaurant = db.session.scalar(
        select(Restaurant).where(Restaurant.name == "The Bower")
    )
    if restaurant is None:
        return _error(
            "Reservations are temporarily unavailable.",
            503,
            "RESERVATIONS_UNAVAILABLE",
        )
    restaurant_id = restaurant.id
    timezone_name = restaurant.timezone
    db.session.rollback()

    parsed_request, validation_error = _reservation_request(payload, timezone_name)
    if validation_error is not None:
        return validation_error
    assert parsed_request is not None

    now = _now(ZoneInfo(timezone_name))
    eligibility_error = _validate_start_window(parsed_request.starts_at, now)
    if eligibility_error is not None:
        return eligibility_error

    with Session(db.engine) as session:
        service = ReservationService(session, restaurant_id)
        try:
            reservation = service.create(parsed_request)
            response_payload = _reservation_payload(reservation, timezone_name)
        except UnsupportedPartySize as error:
            return _error(str(error), 400, "INVALID_PARTY_SIZE", "partySize")
        except ReservationEligibilityError as error:
            return _error(str(error), 400, error.code, error.field)
        except ReservationConflict as conflict:
            return jsonify(
                ok=False,
                code="RESERVATION_CONFLICT",
                message="That table has just been reserved. We can still seat you nearby.",
                alternatives=[_slot_payload(slot) for slot in conflict.alternatives],
            ), 409
        except OperationalError:
            current_app.logger.exception("Reservation database was unavailable")
            return _error(
                "We could not hold that table just now. Please try once more.",
                503,
                "RESERVATIONS_UNAVAILABLE",
            )

    return jsonify(ok=True, reservation=response_payload), 201


@reservation_api.get("/api/reservations/<confirmation_code>")
def reservation_details(confirmation_code: str):
    normalized_code = confirmation_code.strip().upper()
    if not CONFIRMATION_PATTERN.fullmatch(normalized_code):
        return _error("Reservation not found.", 404, "RESERVATION_NOT_FOUND")

    restaurant = db.session.scalar(
        select(Restaurant).where(Restaurant.name == "The Bower")
    )
    if restaurant is None:
        return _error("Reservation not found.", 404, "RESERVATION_NOT_FOUND")
    restaurant_id = restaurant.id
    timezone_name = restaurant.timezone
    db.session.rollback()

    with Session(db.engine) as session:
        service = ReservationService(session, restaurant_id)
        try:
            reservation = service.get_by_confirmation_code(normalized_code)
            response_payload = _reservation_payload(reservation, timezone_name)
        except ReservationNotFound:
            return _error("Reservation not found.", 404, "RESERVATION_NOT_FOUND")

    return jsonify(ok=True, reservation=response_payload)


@reservation_api.post("/api/reservations/<confirmation_code>/cancel")
def cancel_reservation(confirmation_code: str):
    normalized_code = confirmation_code.strip().upper()
    payload = request.get_json(silent=True)
    email = "" if not isinstance(payload, dict) else str(payload.get("email", "")).strip().lower()
    if not CONFIRMATION_PATTERN.fullmatch(normalized_code) or not _valid_email(email):
        return _error("Reservation not found.", 404, "RESERVATION_NOT_FOUND")

    restaurant = db.session.scalar(
        select(Restaurant).where(Restaurant.name == "The Bower")
    )
    if restaurant is None:
        return _error("Reservation not found.", 404, "RESERVATION_NOT_FOUND")
    restaurant_id = restaurant.id
    timezone_name = restaurant.timezone
    db.session.rollback()

    with Session(db.engine) as session:
        service = ReservationService(session, restaurant_id)
        try:
            reservation = service.cancel(normalized_code, email)
            response_payload = _reservation_payload(reservation, timezone_name)
        except ReservationNotFound:
            return _error("Reservation not found.", 404, "RESERVATION_NOT_FOUND")
        except ReservationStateError as error:
            return _error(str(error), 409, "INVALID_RESERVATION_STATE")

    return jsonify(
        ok=True,
        message="Your reservation has been cancelled.",
        reservation=response_payload,
    )


def _reservation_request(
    payload: dict,
    timezone_name: str,
) -> tuple[ReservationRequest | None, tuple | None]:
    service_date = _parse_date(payload.get("date"))
    service_time = _parse_time(payload.get("time"))
    party_size = _parse_party_size(payload.get("partySize"))
    customer = payload.get("customer")
    if service_date is None:
        return None, _error("Choose a valid reservation date.", 400, "INVALID_DATE", "date")
    if service_time is None:
        return None, _error("Choose a valid reservation time.", 400, "INVALID_TIME", "time")
    if party_size is None:
        return None, _error(
            "Choose a supported party size.",
            400,
            "INVALID_PARTY_SIZE",
            "partySize",
        )
    if not isinstance(customer, dict):
        return None, _error(
            "Add the guest contact details.",
            400,
            "INVALID_CUSTOMER",
            "customer",
        )

    name = str(customer.get("name", "")).strip()
    email = str(customer.get("email", "")).strip().lower()
    phone = str(customer.get("phone", "")).strip() or None
    if not name or len(name) > 120:
        return None, _error("Add the guest name.", 400, "INVALID_NAME", "customer.name")
    if not _valid_email(email):
        return None, _error(
            "Add a valid email address.",
            400,
            "INVALID_EMAIL",
            "customer.email",
        )
    if phone is not None and not PHONE_PATTERN.fullmatch(phone):
        return None, _error(
            "Add a valid phone number.",
            400,
            "INVALID_PHONE",
            "customer.phone",
        )

    special_requests = str(payload.get("specialRequests", "")).strip() or None
    if special_requests is not None and len(special_requests) > 2000:
        return None, _error(
            "Special requests must be 2,000 characters or fewer.",
            400,
            "INVALID_SPECIAL_REQUESTS",
            "specialRequests",
        )

    table_id = payload.get("tableId")
    if table_id in (None, ""):
        parsed_table_id = None
    else:
        try:
            parsed_table_id = int(table_id)
        except (TypeError, ValueError):
            return None, _error("Choose a valid table.", 400, "INVALID_TABLE", "tableId")
        if parsed_table_id < 1:
            return None, _error("Choose a valid table.", 400, "INVALID_TABLE", "tableId")

    starts_at = datetime.combine(
        service_date,
        service_time,
        tzinfo=ZoneInfo(timezone_name),
    )
    return ReservationRequest(
        starts_at=starts_at,
        party_size=party_size,
        customer_name=name,
        email=email,
        phone=phone,
        special_requests=special_requests,
        table_id=parsed_table_id,
    ), None


def _reservation_payload(reservation: Reservation, timezone_name: str) -> dict:
    timezone_info = ZoneInfo(timezone_name)
    starts_at = _as_utc(reservation.starts_at).astimezone(timezone_info)
    ends_at = _as_utc(reservation.ends_at).astimezone(timezone_info)
    return {
        "confirmationCode": reservation.confirmation_code,
        "status": reservation.status.value,
        "customer": {
            "name": reservation.customer_name,
            "email": reservation.email,
            "phone": reservation.phone,
        },
        "partySize": reservation.party_size,
        "startsAt": starts_at.isoformat(),
        "endsAt": ends_at.isoformat(),
        "specialRequests": reservation.special_requests,
        "table": None
        if reservation.table is None
        else {
            "id": reservation.table.id,
            "name": reservation.table.display_name,
            "section": reservation.table.section.value,
            "capacity": reservation.table.capacity,
        },
    }


def _slot_payload(slot) -> dict:
    return {
        "time": slot.starts_at.strftime("%H:%M"),
        "startsAt": slot.starts_at.isoformat(),
        "endsAt": slot.ends_at.isoformat(),
        "availableTableCount": len(slot.available_tables),
        "tables": [
            {
                "id": table.id,
                "name": table.display_name,
                "capacity": table.capacity,
                "section": table.section.value,
                "accessible": table.accessible,
            }
            for table in slot.available_tables
        ],
    }


def _validate_date_window(service_date: date, now: datetime):
    if service_date < now.date():
        return _error("That date has already passed.", 400, "DATE_IN_PAST", "date")
    horizon = now.date() + timedelta(
        days=current_app.config["RESERVATION_BOOKING_HORIZON_DAYS"]
    )
    if service_date > horizon:
        return _error(
            "Reservations are not open that far ahead yet.",
            400,
            "DATE_BEYOND_HORIZON",
            "date",
        )
    return None


def _validate_start_window(starts_at: datetime, now: datetime):
    date_error = _validate_date_window(starts_at.date(), now)
    if date_error is not None:
        return date_error
    minimum_start = now + timedelta(
        minutes=current_app.config["RESERVATION_MINIMUM_NOTICE_MINUTES"]
    )
    if starts_at < minimum_start:
        return _error(
            "Please choose a later reservation time.",
            400,
            "INSUFFICIENT_NOTICE",
            "time",
        )
    return None


def _now(timezone_info: ZoneInfo) -> datetime:
    provider = current_app.config.get("RESERVATION_NOW_PROVIDER")
    return provider(timezone_info) if provider is not None else datetime.now(timezone_info)


def _parse_date(value) -> date | None:
    try:
        return date.fromisoformat(str(value))
    except (TypeError, ValueError):
        return None


def _parse_time(value) -> time | None:
    try:
        parsed = time.fromisoformat(str(value))
    except (TypeError, ValueError):
        return None
    if parsed.second or parsed.microsecond or parsed.tzinfo is not None:
        return None
    return parsed


def _parse_party_size(value) -> int | None:
    try:
        parsed = int(value)
    except (TypeError, ValueError):
        return None
    return parsed if parsed > 0 else None


def _valid_email(value: str) -> bool:
    return len(value) <= 254 and EMAIL_PATTERN.fullmatch(value) is not None


def _as_utc(value: datetime) -> datetime:
    if value.tzinfo is None or value.utcoffset() is None:
        return value.replace(tzinfo=timezone.utc)
    return value.astimezone(timezone.utc)


def _error(
    message: str,
    status: int,
    code: str,
    field: str | None = None,
):
    payload = {"ok": False, "code": code, "message": message}
    if field is not None:
        payload["field"] = field
    return jsonify(payload), status
