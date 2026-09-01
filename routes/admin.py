from __future__ import annotations

import hmac
import secrets
from datetime import date, datetime, time, timedelta, timezone
from functools import wraps
from urllib.parse import urljoin, urlparse
from zoneinfo import ZoneInfo

from flask import Blueprint, abort, flash, redirect, render_template, request, session, url_for
from flask_login import current_user, login_required, login_user, logout_user
from sqlalchemy import func, or_, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import selectinload

from extensions import db
from models import (
    ActorType,
    DiningTable,
    OpeningHours,
    Reservation,
    ReservationEvent,
    ReservationEventType,
    ReservationStatus,
    ReservationTimeBlock,
    Restaurant,
    SpecialClosure,
    TableSection,
    TableShape,
    User,
    UserRole,
)
from services import AvailabilityService, AvailabilitySettings


admin = Blueprint("admin", __name__, url_prefix="/admin")
LOGIN_ATTEMPT_LIMIT = 5
LOGIN_LOCK_MINUTES = 15
TERMINAL_STATUSES = {
    ReservationStatus.CANCELLED,
    ReservationStatus.COMPLETED,
    ReservationStatus.NO_SHOW,
}
STATUS_EVENTS = {
    ReservationStatus.CONFIRMED: ReservationEventType.CONFIRMED,
    ReservationStatus.CANCELLED: ReservationEventType.CANCELLED,
    ReservationStatus.CHECKED_IN: ReservationEventType.CHECKED_IN,
    ReservationStatus.COMPLETED: ReservationEventType.COMPLETED,
    ReservationStatus.NO_SHOW: ReservationEventType.NO_SHOW,
}
ALLOWED_TRANSITIONS = {
    ReservationStatus.PENDING: {ReservationStatus.CONFIRMED, ReservationStatus.CANCELLED},
    ReservationStatus.CONFIRMED: {
        ReservationStatus.CHECKED_IN,
        ReservationStatus.CANCELLED,
        ReservationStatus.NO_SHOW,
    },
    ReservationStatus.CHECKED_IN: {ReservationStatus.COMPLETED},
}


def _csrf_token() -> str:
    token = session.get("admin_csrf_token")
    if not token:
        token = secrets.token_urlsafe(32)
        session["admin_csrf_token"] = token
    return token


def _require_csrf() -> None:
    supplied = request.form.get("csrf_token", "")
    expected = session.get("admin_csrf_token", "")
    if not expected or not hmac.compare_digest(supplied, expected):
        abort(400, description="The form expired. Please try again.")


def admin_required(view):
    @wraps(view)
    @login_required
    def wrapped(*args, **kwargs):
        if not current_user.is_admin:
            abort(403)
        return view(*args, **kwargs)

    return wrapped


@admin.context_processor
def admin_context() -> dict:
    return {
        "csrf_token": _csrf_token,
        "ReservationStatus": ReservationStatus,
        "UserRole": UserRole,
    }


@admin.errorhandler(400)
@admin.errorhandler(403)
def admin_error(error):
    return render_template(
        "admin/error.html",
        status=error.code,
        message=(
            "The form expired. Please return and try again."
            if error.code == 400
            else "Your account does not have permission to do that."
        ),
    ), error.code


def _restaurant() -> Restaurant:
    restaurant = db.session.scalar(select(Restaurant).where(Restaurant.name == "The Bower"))
    if restaurant is None:
        abort(503)
    return restaurant


def _safe_next(value: str | None) -> str | None:
    if not value:
        return None
    target = urlparse(urljoin(request.host_url, value))
    return value if target.netloc == urlparse(request.host_url).netloc else None


@admin.route("/login", methods=["GET", "POST"])
def login():
    if current_user.is_authenticated:
        return redirect(url_for("admin.dashboard"))
    if request.method == "POST":
        _require_csrf()
        email = request.form.get("email", "").strip().lower()
        password = request.form.get("password", "")
        user = db.session.scalar(select(User).where(User.email == email))
        now = datetime.now(timezone.utc)

        if user is not None and user.is_locked(now):
            flash("Too many sign-in attempts. Try again in fifteen minutes.", "error")
        elif user is not None and user.active and user.check_password(password):
            user.failed_login_attempts = 0
            user.locked_until = None
            user.last_login_at = now
            db.session.commit()
            session.clear()
            session.permanent = True
            login_user(user)
            _csrf_token()
            return redirect(_safe_next(request.args.get("next")) or url_for("admin.dashboard"))
        else:
            if user is not None:
                user.failed_login_attempts += 1
                if user.failed_login_attempts >= LOGIN_ATTEMPT_LIMIT:
                    user.locked_until = now + timedelta(minutes=LOGIN_LOCK_MINUTES)
                db.session.commit()
            flash("The email or password was not recognized.", "error")

    return render_template("admin/login.html")


@admin.post("/logout")
@login_required
def logout():
    _require_csrf()
    logout_user()
    session.clear()
    return redirect(url_for("admin.login"))


@admin.get("")
@login_required
def dashboard():
    restaurant = _restaurant()
    local_timezone = ZoneInfo(restaurant.timezone)
    selected_date = _parse_date(request.args.get("date")) or datetime.now(local_timezone).date()
    day_start = datetime.combine(selected_date, time.min, tzinfo=local_timezone).astimezone(timezone.utc)
    day_end = day_start + timedelta(days=1)
    search_term = request.args.get("q", "").strip()
    statement = (
        select(Reservation)
        .options(selectinload(Reservation.table))
        .where(Reservation.starts_at >= day_start, Reservation.starts_at < day_end)
        .order_by(Reservation.starts_at)
    )
    if search_term:
        like = f"%{search_term}%"
        statement = statement.where(
            or_(
                Reservation.customer_name.ilike(like),
                Reservation.confirmation_code.ilike(like),
                Reservation.phone.ilike(like),
            )
        )
    reservations = tuple(db.session.scalars(statement))
    active = tuple(r for r in reservations if r.status not in TERMINAL_STATUSES)
    total_seats = db.session.scalar(
        select(func.sum(DiningTable.capacity)).where(
            DiningTable.restaurant_id == restaurant.id,
            DiningTable.active.is_(True),
        )
    ) or 0
    metrics = {
        "reservations": len(active),
        "guests": sum(r.party_size for r in active),
        "cancellations": sum(r.status == ReservationStatus.CANCELLED for r in reservations),
        "no_shows": sum(r.status == ReservationStatus.NO_SHOW for r in reservations),
        "occupancy": _peak_occupancy(active, total_seats),
    }
    return render_template(
        "admin/dashboard.html",
        selected_date=selected_date,
        reservations=reservations,
        metrics=metrics,
        search_term=search_term,
        local_timezone=local_timezone,
        timezone=timezone,
    )


@admin.get("/reservations/<confirmation_code>")
@login_required
def reservation_detail(confirmation_code: str):
    reservation = db.session.scalar(
        select(Reservation)
        .options(
            selectinload(Reservation.table),
            selectinload(Reservation.events),
            selectinload(Reservation.notification_jobs),
        )
        .where(Reservation.confirmation_code == confirmation_code.upper())
    )
    if reservation is None:
        abort(404)
    restaurant = _restaurant()
    tables = tuple(
        db.session.scalars(
            select(DiningTable)
            .where(DiningTable.restaurant_id == restaurant.id, DiningTable.active.is_(True))
            .order_by(DiningTable.capacity, DiningTable.display_name)
        )
    )
    return render_template(
        "admin/reservation_detail.html",
        reservation=reservation,
        tables=tables,
        local_timezone=ZoneInfo(restaurant.timezone),
        allowed_statuses=ALLOWED_TRANSITIONS.get(reservation.status, set()),
        timezone=timezone,
    )


@admin.post("/reservations/<confirmation_code>/status")
@login_required
def reservation_status(confirmation_code: str):
    _require_csrf()
    reservation = db.session.scalar(
        select(Reservation).where(Reservation.confirmation_code == confirmation_code.upper())
    )
    if reservation is None:
        abort(404)
    try:
        new_status = ReservationStatus(request.form.get("status", ""))
    except ValueError:
        abort(400)
    if new_status not in ALLOWED_TRANSITIONS.get(reservation.status, set()):
        abort(400)
    reservation.status = new_status
    if new_status in TERMINAL_STATUSES:
        reservation.time_blocks.clear()
    reservation.events.append(
        ReservationEvent(
            event_type=STATUS_EVENTS[new_status],
            actor_type=ActorType.STAFF,
            actor_reference=current_user.email,
            event_metadata={"source": "admin"},
        )
    )
    db.session.commit()
    flash(f"Reservation marked {new_status.value.replace('_', ' ').lower()}.", "success")
    return redirect(url_for("admin.reservation_detail", confirmation_code=confirmation_code))


@admin.post("/reservations/<confirmation_code>/edit")
@login_required
def edit_reservation(confirmation_code: str):
    _require_csrf()
    reservation = db.session.scalar(
        select(Reservation)
        .options(selectinload(Reservation.time_blocks))
        .where(Reservation.confirmation_code == confirmation_code.upper())
    )
    if reservation is None:
        abort(404)
    name = request.form.get("customer_name", "").strip()
    phone = request.form.get("phone", "").strip() or None
    requests_note = request.form.get("special_requests", "").strip() or None
    if not name or len(name) > 120 or (requests_note and len(requests_note) > 2000):
        abort(400)

    new_table_id = _parse_positive_int(request.form.get("table_id"))
    if new_table_id is None:
        abort(400)
    if new_table_id != reservation.dining_table_id:
        restaurant = _restaurant()
        available = AvailabilityService(db.session, restaurant.id).find_available_tables(
            _as_utc(reservation.starts_at), reservation.party_size
        )
        selected_table = next((table for table in available if table.id == new_table_id), None)
        if selected_table is None:
            flash("That table is not available for this reservation.", "error")
            return redirect(url_for("admin.reservation_detail", confirmation_code=confirmation_code))
        previous_table = reservation.table.display_name if reservation.table else "Unassigned"
        reservation.time_blocks.clear()
        db.session.flush()
        reservation.table = selected_table
        _claim_reservation_blocks(reservation, selected_table.id)
        reservation.events.append(
            ReservationEvent(
                event_type=ReservationEventType.TABLE_CHANGED,
                actor_type=ActorType.STAFF,
                actor_reference=current_user.email,
                event_metadata={"from": previous_table, "to": selected_table.display_name},
            )
        )

    reservation.customer_name = name
    reservation.phone = phone
    reservation.special_requests = requests_note
    reservation.events.append(
        ReservationEvent(
            event_type=ReservationEventType.MODIFIED,
            actor_type=ActorType.STAFF,
            actor_reference=current_user.email,
            event_metadata={"source": "admin"},
        )
    )
    try:
        db.session.commit()
    except IntegrityError:
        db.session.rollback()
        flash("That table was claimed by another reservation.", "error")
        return redirect(url_for("admin.reservation_detail", confirmation_code=confirmation_code))
    flash("Reservation details updated.", "success")
    return redirect(url_for("admin.reservation_detail", confirmation_code=confirmation_code))


@admin.route("/tables", methods=["GET", "POST"])
@admin_required
def tables():
    restaurant = _restaurant()
    if request.method == "POST":
        _require_csrf()
        try:
            table = _table_from_form(restaurant.id)
        except (TypeError, ValueError):
            flash("Use a name, positive capacity, and positions from 0 to 100.", "error")
            return redirect(url_for("admin.tables"))
        db.session.add(table)
        try:
            db.session.commit()
            flash("Table added to the dining room.", "success")
        except IntegrityError:
            db.session.rollback()
            flash("Use a unique table name and valid values.", "error")
        return redirect(url_for("admin.tables"))
    all_tables = tuple(
        db.session.scalars(
            select(DiningTable).where(DiningTable.restaurant_id == restaurant.id).order_by(DiningTable.display_name)
        )
    )
    return render_template("admin/tables.html", tables=all_tables, sections=TableSection, shapes=TableShape)


@admin.post("/tables/<int:table_id>")
@admin_required
def edit_table(table_id: int):
    _require_csrf()
    table = db.session.get(DiningTable, table_id)
    if table is None:
        abort(404)
    try:
        values = _table_values()
    except (TypeError, ValueError):
        flash("Use a name, positive capacity, and positions from 0 to 100.", "error")
        return redirect(url_for("admin.tables"))
    table.display_name = values["display_name"]
    table.capacity = values["capacity"]
    table.section = values["section"]
    table.shape = values["shape"]
    table.x_position = values["x_position"]
    table.y_position = values["y_position"]
    table.accessible = values["accessible"]
    table.active = values["active"]
    try:
        db.session.commit()
        flash("Table updated.", "success")
    except IntegrityError:
        db.session.rollback()
        flash("The table values could not be saved.", "error")
    return redirect(url_for("admin.tables"))


@admin.route("/hours", methods=["GET", "POST"])
@admin_required
def hours():
    restaurant = _restaurant()
    if request.method == "POST":
        _require_csrf()
        try:
            period_id = _parse_positive_int(request.form.get("period_id"))
            if period_id is None:
                day_of_week = int(request.form.get("day_of_week", "-1"))
                if not 0 <= day_of_week <= 6:
                    raise ValueError
                period = OpeningHours(restaurant_id=restaurant.id, day_of_week=day_of_week)
                db.session.add(period)
            else:
                period = db.session.get(OpeningHours, period_id)
                if period is None or period.restaurant_id != restaurant.id:
                    abort(404)
            period.opens_at = _parse_time(request.form.get("opens_at"))
            period.closes_at = _parse_time(request.form.get("closes_at"))
            period.last_seating_at = _parse_time(request.form.get("last_seating_at"))
            period.active = request.form.get("active") == "on"
            db.session.commit()
            flash("Opening period updated.", "success")
        except (IntegrityError, ValueError):
            db.session.rollback()
            flash("Check that opening, last seating, and closing times are in order.", "error")
        return redirect(url_for("admin.hours"))
    periods = tuple(
        db.session.scalars(
            select(OpeningHours).where(OpeningHours.restaurant_id == restaurant.id).order_by(
                OpeningHours.day_of_week, OpeningHours.opens_at
            )
        )
    )
    return render_template("admin/hours.html", periods=periods)


@admin.route("/closures", methods=["GET", "POST"])
@admin_required
def closures():
    restaurant = _restaurant()
    if request.method == "POST":
        _require_csrf()
        try:
            full_day = request.form.get("full_day") == "on"
            closure = SpecialClosure(
                restaurant_id=restaurant.id,
                date=date.fromisoformat(request.form.get("date", "")),
                reason=request.form.get("reason", "").strip(),
                full_day=full_day,
                starts_at=None if full_day else _parse_time(request.form.get("starts_at")),
                ends_at=None if full_day else _parse_time(request.form.get("ends_at")),
            )
            if not closure.reason:
                raise ValueError
            db.session.add(closure)
            db.session.commit()
            flash("Closure added. Customer availability now reflects it.", "success")
        except (IntegrityError, ValueError):
            db.session.rollback()
            flash("The closure window is invalid.", "error")
        return redirect(url_for("admin.closures"))
    upcoming = tuple(
        db.session.scalars(
            select(SpecialClosure)
            .where(SpecialClosure.restaurant_id == restaurant.id, SpecialClosure.date >= date.today())
            .order_by(SpecialClosure.date)
        )
    )
    return render_template("admin/closures.html", closures=upcoming)


@admin.post("/closures/<int:closure_id>/delete")
@admin_required
def delete_closure(closure_id: int):
    _require_csrf()
    closure = db.session.get(SpecialClosure, closure_id)
    if closure is None:
        abort(404)
    db.session.delete(closure)
    db.session.commit()
    flash("Closure removed. Availability has been reopened.", "success")
    return redirect(url_for("admin.closures"))


@admin.route("/staff", methods=["GET", "POST"])
@admin_required
def staff():
    if request.method == "POST":
        _require_csrf()
        try:
            user = User(
                name=request.form.get("name", "").strip(),
                email=request.form.get("email", "").strip().lower(),
                role=UserRole(request.form.get("role", "STAFF")),
            )
            if not user.name or "@" not in user.email:
                raise ValueError
            user.set_password(request.form.get("password", ""))
            db.session.add(user)
            db.session.commit()
            flash("Staff account created.", "success")
        except (IntegrityError, ValueError):
            db.session.rollback()
            flash("Use a unique email and a password of at least 12 characters.", "error")
        return redirect(url_for("admin.staff"))
    users = tuple(db.session.scalars(select(User).order_by(User.name)))
    return render_template("admin/staff.html", users=users)


@admin.post("/staff/<int:user_id>/toggle")
@admin_required
def toggle_staff(user_id: int):
    _require_csrf()
    user = db.session.get(User, user_id)
    if user is None:
        abort(404)
    if user.id == current_user.id:
        flash("You cannot deactivate your own signed-in account.", "error")
    else:
        user.active = not user.active
        db.session.commit()
        flash("Staff access updated.", "success")
    return redirect(url_for("admin.staff"))


def _table_values() -> dict:
    values = {
        "display_name": request.form.get("display_name", "").strip(),
        "capacity": int(request.form.get("capacity", "0")),
        "section": TableSection(request.form.get("section", "")),
        "shape": TableShape(request.form.get("shape", "")),
        "x_position": float(request.form.get("x_position", "-1")),
        "y_position": float(request.form.get("y_position", "-1")),
        "accessible": request.form.get("accessible") == "on",
        "active": request.form.get("active") == "on",
    }
    if (
        not values["display_name"]
        or values["capacity"] < 1
        or not 0 <= values["x_position"] <= 100
        or not 0 <= values["y_position"] <= 100
    ):
        raise ValueError("Invalid table values.")
    return values


def _table_from_form(restaurant_id: int) -> DiningTable:
    return DiningTable(restaurant_id=restaurant_id, **_table_values())


def _claim_reservation_blocks(reservation: Reservation, table_id: int) -> None:
    settings = AvailabilitySettings()
    block_start = _as_utc(reservation.starts_at)
    claim_end = _as_utc(reservation.ends_at) + settings.reset_buffer
    while block_start < claim_end:
        reservation.time_blocks.append(
            ReservationTimeBlock(dining_table_id=table_id, starts_at=block_start)
        )
        block_start += settings.slot_interval


def _as_utc(value: datetime) -> datetime:
    return value.replace(tzinfo=timezone.utc) if value.tzinfo is None else value.astimezone(timezone.utc)


def _parse_date(value: str | None) -> date | None:
    try:
        return date.fromisoformat(value or "")
    except ValueError:
        return None


def _parse_time(value: str | None) -> time:
    return time.fromisoformat(value or "")


def _parse_positive_int(value: str | None) -> int | None:
    try:
        parsed = int(value or "")
    except ValueError:
        return None
    return parsed if parsed > 0 else None


def _peak_occupancy(reservations: tuple[Reservation, ...], total_seats: int) -> int:
    if not reservations or total_seats < 1:
        return 0
    seat_counts: dict[datetime, int] = {}
    interval = timedelta(minutes=15)
    for reservation in reservations:
        cursor = _as_utc(reservation.starts_at)
        end = _as_utc(reservation.ends_at)
        while cursor < end:
            seat_counts[cursor] = seat_counts.get(cursor, 0) + reservation.party_size
            cursor += interval
    return min(100, round(max(seat_counts.values(), default=0) / total_seats * 100))
