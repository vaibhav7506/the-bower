from __future__ import annotations

from datetime import datetime
from enum import Enum

from sqlalchemy import DateTime, Enum as SqlEnum, ForeignKey, Index, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from extensions import db
from .mixins import TimestampMixin, utc_now


class NotificationKind(str, Enum):
    BOOKING_CONFIRMATION = "BOOKING_CONFIRMATION"
    CANCELLATION_CONFIRMATION = "CANCELLATION_CONFIRMATION"
    RESERVATION_REMINDER = "RESERVATION_REMINDER"


class NotificationStatus(str, Enum):
    PENDING = "PENDING"
    PROCESSING = "PROCESSING"
    RETRY_PENDING = "RETRY_PENDING"
    SENT = "SENT"
    FAILED = "FAILED"


class NotificationJob(TimestampMixin, db.Model):
    __tablename__ = "notification_jobs"
    __table_args__ = (
        Index("ix_notification_jobs_dispatch", "status", "run_after"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    reservation_id: Mapped[int] = mapped_column(
        ForeignKey("reservations.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    kind: Mapped[NotificationKind] = mapped_column(
        SqlEnum(NotificationKind, native_enum=False, length=32),
        nullable=False,
    )
    status: Mapped[NotificationStatus] = mapped_column(
        SqlEnum(NotificationStatus, native_enum=False, length=20),
        nullable=False,
        default=NotificationStatus.PENDING,
    )
    dedupe_key: Mapped[str] = mapped_column(String(80), nullable=False, unique=True)
    attempts: Mapped[int] = mapped_column(nullable=False, default=0)
    run_after: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        default=utc_now,
    )
    sent_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    last_error: Mapped[str | None] = mapped_column(Text)

    reservation = relationship("Reservation", back_populates="notification_jobs")
