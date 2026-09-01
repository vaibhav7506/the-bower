from __future__ import annotations

import logging
import smtplib
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from email.message import EmailMessage
from zoneinfo import ZoneInfo

from flask import Flask, current_app
from sqlalchemy import select, text
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session, selectinload

from extensions import db
from models import (
    NotificationJob,
    NotificationKind,
    NotificationStatus,
    Reservation,
    ReservationStatus,
    DiningTable,
)


LOGGER = logging.getLogger(__name__)
EXECUTOR = ThreadPoolExecutor(max_workers=2, thread_name_prefix="bower-notifications")
DISPATCHABLE_STATUSES = (NotificationStatus.PENDING, NotificationStatus.RETRY_PENDING)


@dataclass(frozen=True, slots=True)
class RenderedNotification:
    recipient: str
    subject: str
    text_body: str


class NotificationService:
    def __init__(self, session: Session) -> None:
        self.session = session

    def enqueue(self, reservation_id: int, kind: NotificationKind) -> NotificationJob:
        dedupe_key = f"reservation:{reservation_id}:{kind.value}"
        existing = self.session.scalar(
            select(NotificationJob).where(NotificationJob.dedupe_key == dedupe_key)
        )
        if existing is not None:
            return existing
        job = NotificationJob(
            reservation_id=reservation_id,
            kind=kind,
            status=NotificationStatus.PENDING,
            dedupe_key=dedupe_key,
            run_after=datetime.now(timezone.utc),
        )
        self.session.add(job)
        try:
            self.session.commit()
        except IntegrityError:
            self.session.rollback()
            existing = self.session.scalar(
                select(NotificationJob).where(NotificationJob.dedupe_key == dedupe_key)
            )
            if existing is None:
                raise
            return existing
        return job

    def enqueue_due_reminders(self, now: datetime | None = None) -> tuple[int, ...]:
        current = now or datetime.now(timezone.utc)
        window_start = current + timedelta(hours=23)
        window_end = current + timedelta(hours=25)
        reservation_ids = tuple(
            self.session.scalars(
                select(Reservation.id).where(
                    Reservation.status == ReservationStatus.CONFIRMED,
                    Reservation.starts_at >= window_start,
                    Reservation.starts_at < window_end,
                )
            )
        )
        jobs = tuple(
            self.enqueue(reservation_id, NotificationKind.RESERVATION_REMINDER)
            for reservation_id in reservation_ids
        )
        return tuple(job.id for job in jobs)


def dispatch_job_async(app: Flask, job_id: int) -> None:
    if not app.config.get("NOTIFICATION_AUTO_DISPATCH", True):
        return

    def run() -> None:
        with app.app_context():
            process_notification_job(job_id)

    EXECUTOR.submit(run)


def process_due_notifications(limit: int = 25) -> int:
    now = datetime.now(timezone.utc)
    job_ids = tuple(
        db.session.scalars(
            select(NotificationJob.id)
            .where(
                NotificationJob.status.in_(DISPATCHABLE_STATUSES),
                NotificationJob.run_after <= now,
            )
            .order_by(NotificationJob.run_after)
            .limit(limit)
        )
    )
    db.session.rollback()
    for job_id in job_ids:
        process_notification_job(job_id)
    return len(job_ids)


def process_notification_job(job_id: int) -> NotificationStatus | None:
    with Session(db.engine) as session:
        _begin_write(session)
        job = session.get(NotificationJob, job_id)
        now = datetime.now(timezone.utc)
        if job is None or job.status not in DISPATCHABLE_STATUSES or _as_utc(job.run_after) > now:
            session.rollback()
            return None
        job.status = NotificationStatus.PROCESSING
        job.attempts += 1
        session.commit()

    try:
        with Session(db.engine) as session:
            job = session.scalar(
                select(NotificationJob)
                .options(
                    selectinload(NotificationJob.reservation)
                    .selectinload(Reservation.table)
                    .selectinload(DiningTable.restaurant)
                )
                .where(NotificationJob.id == job_id)
            )
            if job is None:
                return None
            rendered = render_notification(job)
        deliver_notification(rendered)
    except Exception as error:
        LOGGER.warning("Notification job %s failed: %s", job_id, type(error).__name__)
        with Session(db.engine) as session:
            job = session.get(NotificationJob, job_id)
            if job is None:
                return None
            maximum_attempts = int(current_app.config.get("NOTIFICATION_MAX_ATTEMPTS", 5))
            job.last_error = "Delivery provider was unavailable."
            if job.attempts >= maximum_attempts:
                job.status = NotificationStatus.FAILED
            else:
                job.status = NotificationStatus.RETRY_PENDING
                delay_minutes = min(60, 2 ** max(0, job.attempts - 1))
                job.run_after = datetime.now(timezone.utc) + timedelta(minutes=delay_minutes)
            session.commit()
            return job.status

    with Session(db.engine) as session:
        job = session.get(NotificationJob, job_id)
        if job is None:
            return None
        job.status = NotificationStatus.SENT
        job.sent_at = datetime.now(timezone.utc)
        job.last_error = None
        session.commit()
        return job.status


def render_notification(job: NotificationJob) -> RenderedNotification:
    reservation = job.reservation
    timezone_name = reservation.table.restaurant.timezone if reservation.table else "Asia/Kolkata"
    starts_at = _as_utc(reservation.starts_at).astimezone(ZoneInfo(timezone_name))
    when = starts_at.strftime("%A, %d %B %Y at %I:%M %p")
    base_url = current_app.config["PUBLIC_BASE_URL"]
    management_url = f"{base_url}/api/reservations/{reservation.confirmation_code}"
    common = (
        f"Reservation: {reservation.confirmation_code}\n"
        f"Date and time: {when}\n"
        f"Party size: {reservation.party_size}\n"
        f"Manage this reservation: {management_url}\n"
    )
    if job.kind == NotificationKind.BOOKING_CONFIRMATION:
        subject = f"Your table at The Bower · {reservation.confirmation_code}"
        body = f"Hello {reservation.customer_name},\n\nYour reservation is confirmed.\n\n{common}\nWe look forward to welcoming you."
    elif job.kind == NotificationKind.CANCELLATION_CONFIRMATION:
        subject = f"Reservation cancelled · {reservation.confirmation_code}"
        body = f"Hello {reservation.customer_name},\n\nYour reservation at The Bower has been cancelled.\n\n{common}"
    else:
        subject = f"A reminder from The Bower · {reservation.confirmation_code}"
        body = f"Hello {reservation.customer_name},\n\nWe look forward to welcoming you tomorrow.\n\n{common}"
    return RenderedNotification(reservation.email, subject, body)


def deliver_notification(notification: RenderedNotification) -> None:
    config = current_app.config
    mode = config.get("NOTIFICATION_DELIVERY_MODE", "log")
    if mode == "fail":
        raise RuntimeError("Configured test delivery failure")
    if mode == "log":
        LOGGER.info("Notification queued for %s: %s", notification.recipient, notification.subject)
        return
    if mode != "smtp":
        raise RuntimeError("Unsupported notification delivery mode")

    host = config.get("SMTP_HOST")
    sender = config.get("NOTIFICATION_FROM_EMAIL")
    if not host or not sender:
        raise RuntimeError("SMTP delivery is not configured")
    message = EmailMessage()
    message["From"] = sender
    message["To"] = notification.recipient
    message["Subject"] = notification.subject
    message.set_content(notification.text_body)
    with smtplib.SMTP(host, int(config.get("SMTP_PORT", 587)), timeout=15) as client:
        if config.get("SMTP_STARTTLS", True):
            client.starttls()
        username = config.get("SMTP_USERNAME")
        password = config.get("SMTP_PASSWORD")
        if username and password:
            client.login(username, password)
        client.send_message(message)


def _begin_write(session: Session) -> None:
    if session.get_bind().dialect.name == "sqlite":
        session.execute(text("BEGIN IMMEDIATE"))
    else:
        session.begin()


def _as_utc(value: datetime) -> datetime:
    return value.replace(tzinfo=timezone.utc) if value.tzinfo is None else value.astimezone(timezone.utc)
