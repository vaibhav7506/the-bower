from __future__ import annotations

from datetime import datetime
from enum import Enum

from sqlalchemy import CheckConstraint, DateTime, Enum as SqlEnum, ForeignKey, Index, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from extensions import db
from .mixins import TimestampMixin


class ReservationStatus(str, Enum):
    PENDING = "PENDING"
    CONFIRMED = "CONFIRMED"
    CANCELLED = "CANCELLED"
    COMPLETED = "COMPLETED"
    NO_SHOW = "NO_SHOW"
    CHECKED_IN = "CHECKED_IN"


class Reservation(TimestampMixin, db.Model):
    __tablename__ = "reservations"
    __table_args__ = (
        CheckConstraint("party_size > 0", name="ck_reservation_party_size_positive"),
        CheckConstraint("starts_at < ends_at", name="ck_reservation_time_range"),
        Index("ix_reservations_service_window", "starts_at", "ends_at", "status"),
        Index(
            "ix_reservations_table_window",
            "dining_table_id",
            "starts_at",
            "ends_at",
            "status",
        ),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    confirmation_code: Mapped[str] = mapped_column(
        String(16),
        nullable=False,
        unique=True,
        index=True,
    )
    customer_id: Mapped[int] = mapped_column(
        ForeignKey("customers.id", ondelete="RESTRICT"),
        nullable=False,
    )
    dining_table_id: Mapped[int | None] = mapped_column(
        ForeignKey("dining_tables.id", ondelete="RESTRICT"),
        index=True,
    )
    customer_name: Mapped[str] = mapped_column(String(120), nullable=False)
    email: Mapped[str] = mapped_column(String(254), nullable=False)
    phone: Mapped[str | None] = mapped_column(String(32))
    party_size: Mapped[int] = mapped_column(nullable=False)
    starts_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    ends_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    status: Mapped[ReservationStatus] = mapped_column(
        SqlEnum(ReservationStatus, native_enum=False, length=16),
        nullable=False,
        default=ReservationStatus.PENDING,
    )
    special_requests: Mapped[str | None] = mapped_column(Text)

    customer = relationship("Customer", back_populates="reservations")
    table = relationship("DiningTable", back_populates="reservations")
    events = relationship(
        "ReservationEvent",
        back_populates="reservation",
        cascade="all, delete-orphan",
        order_by="ReservationEvent.occurred_at",
    )
