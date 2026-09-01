from __future__ import annotations

from datetime import date, time

from sqlalchemy import Boolean, CheckConstraint, Date, ForeignKey, Index, String, Time, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column, relationship

from extensions import db
from .mixins import TimestampMixin


class OpeningHours(TimestampMixin, db.Model):
    __tablename__ = "opening_hours"
    __table_args__ = (
        UniqueConstraint(
            "restaurant_id",
            "day_of_week",
            "opens_at",
            name="uq_opening_hours_service",
        ),
        CheckConstraint("day_of_week >= 0 AND day_of_week <= 6", name="ck_opening_hours_day"),
        CheckConstraint("opens_at < closes_at", name="ck_opening_hours_range"),
        CheckConstraint(
            "last_seating_at >= opens_at AND last_seating_at <= closes_at",
            name="ck_opening_hours_last_seating",
        ),
        Index("ix_opening_hours_lookup", "restaurant_id", "day_of_week", "active"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    restaurant_id: Mapped[int] = mapped_column(
        ForeignKey("restaurants.id", ondelete="CASCADE"),
        nullable=False,
    )
    day_of_week: Mapped[int] = mapped_column(nullable=False)
    opens_at: Mapped[time] = mapped_column(Time, nullable=False)
    closes_at: Mapped[time] = mapped_column(Time, nullable=False)
    last_seating_at: Mapped[time] = mapped_column(Time, nullable=False)
    active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)

    restaurant = relationship("Restaurant", back_populates="opening_hours")


class SpecialClosure(TimestampMixin, db.Model):
    __tablename__ = "special_closures"
    __table_args__ = (
        CheckConstraint(
            "full_day = 1 OR (starts_at IS NOT NULL AND ends_at IS NOT NULL)",
            name="ck_special_closure_window",
        ),
        CheckConstraint(
            "starts_at IS NULL OR ends_at IS NULL OR starts_at < ends_at",
            name="ck_special_closure_range",
        ),
        Index("ix_special_closures_lookup", "restaurant_id", "date"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    restaurant_id: Mapped[int] = mapped_column(
        ForeignKey("restaurants.id", ondelete="CASCADE"),
        nullable=False,
    )
    date: Mapped[date] = mapped_column(Date, nullable=False)
    reason: Mapped[str] = mapped_column(String(240), nullable=False)
    full_day: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    starts_at: Mapped[time | None] = mapped_column(Time)
    ends_at: Mapped[time | None] = mapped_column(Time)

    restaurant = relationship("Restaurant", back_populates="special_closures")
