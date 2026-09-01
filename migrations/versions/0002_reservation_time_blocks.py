"""Add transaction-safe reservation time blocks.

Revision ID: 0002_reservation_time_blocks
Revises: 0001_reservation_domain
"""
from __future__ import annotations

from alembic import op
import sqlalchemy as sa


revision = "0002_reservation_time_blocks"
down_revision = "0001_reservation_domain"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "reservation_time_blocks",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column(
            "reservation_id",
            sa.Integer(),
            sa.ForeignKey("reservations.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "dining_table_id",
            sa.Integer(),
            sa.ForeignKey("dining_tables.id", ondelete="RESTRICT"),
            nullable=False,
        ),
        sa.Column("starts_at", sa.DateTime(timezone=True), nullable=False),
        sa.UniqueConstraint(
            "dining_table_id",
            "starts_at",
            name="uq_reservation_time_block_claim",
        ),
    )
    op.create_index(
        "ix_reservation_time_blocks_reservation",
        "reservation_time_blocks",
        ["reservation_id"],
    )


def downgrade() -> None:
    op.drop_table("reservation_time_blocks")
