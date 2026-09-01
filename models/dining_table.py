from __future__ import annotations

from enum import Enum

from sqlalchemy import Boolean, CheckConstraint, Enum as SqlEnum, Float, ForeignKey, Index, String, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column, relationship

from extensions import db
from .mixins import TimestampMixin


class TableSection(str, Enum):
    MAIN_DINING = "MAIN_DINING"
    WINDOW = "WINDOW"
    PRIVATE = "PRIVATE"
    BAR = "BAR"
    TERRACE = "TERRACE"


class TableShape(str, Enum):
    ROUND = "ROUND"
    SQUARE = "SQUARE"
    RECTANGLE = "RECTANGLE"
    BAR = "BAR"


class DiningTable(TimestampMixin, db.Model):
    __tablename__ = "dining_tables"
    __table_args__ = (
        UniqueConstraint("restaurant_id", "display_name", name="uq_table_restaurant_name"),
        CheckConstraint("capacity > 0", name="ck_table_capacity_positive"),
        CheckConstraint("x_position >= 0 AND x_position <= 100", name="ck_table_x_position"),
        CheckConstraint("y_position >= 0 AND y_position <= 100", name="ck_table_y_position"),
        Index("ix_dining_tables_restaurant_active", "restaurant_id", "active"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    restaurant_id: Mapped[int] = mapped_column(
        ForeignKey("restaurants.id", ondelete="CASCADE"),
        nullable=False,
    )
    display_name: Mapped[str] = mapped_column(String(40), nullable=False)
    capacity: Mapped[int] = mapped_column(nullable=False)
    section: Mapped[TableSection] = mapped_column(
        SqlEnum(TableSection, native_enum=False, length=24),
        nullable=False,
    )
    x_position: Mapped[float] = mapped_column(Float, nullable=False)
    y_position: Mapped[float] = mapped_column(Float, nullable=False)
    shape: Mapped[TableShape] = mapped_column(
        SqlEnum(TableShape, native_enum=False, length=16),
        nullable=False,
    )
    active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    accessible: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)

    restaurant = relationship("Restaurant", back_populates="tables")
    reservations = relationship("Reservation", back_populates="table")
