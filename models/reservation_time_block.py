from __future__ import annotations

from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, Index, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column, relationship

from extensions import db


class ReservationTimeBlock(db.Model):
    __tablename__ = "reservation_time_blocks"
    __table_args__ = (
        UniqueConstraint(
            "dining_table_id",
            "starts_at",
            name="uq_reservation_time_block_claim",
        ),
        Index(
            "ix_reservation_time_blocks_reservation",
            "reservation_id",
        ),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    reservation_id: Mapped[int] = mapped_column(
        ForeignKey("reservations.id", ondelete="CASCADE"),
        nullable=False,
    )
    dining_table_id: Mapped[int] = mapped_column(
        ForeignKey("dining_tables.id", ondelete="RESTRICT"),
        nullable=False,
    )
    starts_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
    )

    reservation = relationship("Reservation", back_populates="time_blocks")
    table = relationship("DiningTable")
