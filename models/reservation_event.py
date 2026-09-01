from __future__ import annotations

from datetime import datetime
from enum import Enum
from typing import Any

from sqlalchemy import DateTime, Enum as SqlEnum, ForeignKey, Index, JSON, String
from sqlalchemy.orm import Mapped, mapped_column, relationship

from extensions import db
from .mixins import utc_now


class ReservationEventType(str, Enum):
    CREATED = "CREATED"
    CONFIRMED = "CONFIRMED"
    MODIFIED = "MODIFIED"
    TABLE_CHANGED = "TABLE_CHANGED"
    CANCELLED = "CANCELLED"
    CHECKED_IN = "CHECKED_IN"
    COMPLETED = "COMPLETED"
    NO_SHOW = "NO_SHOW"


class ActorType(str, Enum):
    CUSTOMER = "CUSTOMER"
    STAFF = "STAFF"
    SYSTEM = "SYSTEM"


class ReservationEvent(db.Model):
    __tablename__ = "reservation_events"
    __table_args__ = (
        Index("ix_reservation_events_history", "reservation_id", "occurred_at"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    reservation_id: Mapped[int] = mapped_column(
        ForeignKey("reservations.id", ondelete="CASCADE"),
        nullable=False,
    )
    event_type: Mapped[ReservationEventType] = mapped_column(
        SqlEnum(ReservationEventType, native_enum=False, length=24),
        nullable=False,
    )
    actor_type: Mapped[ActorType] = mapped_column(
        SqlEnum(ActorType, native_enum=False, length=16),
        nullable=False,
    )
    actor_reference: Mapped[str | None] = mapped_column(String(120))
    event_metadata: Mapped[dict[str, Any]] = mapped_column(
        "metadata",
        JSON,
        nullable=False,
        default=dict,
    )
    occurred_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        default=utc_now,
    )

    reservation = relationship("Reservation", back_populates="events")
