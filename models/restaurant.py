from __future__ import annotations

from sqlalchemy import String
from sqlalchemy.orm import Mapped, mapped_column, relationship

from extensions import db
from .mixins import TimestampMixin


class Restaurant(TimestampMixin, db.Model):
    __tablename__ = "restaurants"

    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(120), nullable=False)
    timezone: Mapped[str] = mapped_column(
        String(64),
        nullable=False,
        default="Asia/Kolkata",
    )
    currency_code: Mapped[str] = mapped_column(
        String(3),
        nullable=False,
        default="INR",
    )

    tables = relationship("DiningTable", back_populates="restaurant")
    opening_hours = relationship("OpeningHours", back_populates="restaurant")
    special_closures = relationship("SpecialClosure", back_populates="restaurant")
