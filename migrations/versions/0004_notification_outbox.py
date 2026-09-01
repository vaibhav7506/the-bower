"""Add the durable notification outbox.

Revision ID: 0004_notification_outbox
Revises: 0003_admin_users
"""
from __future__ import annotations

from alembic import op
import sqlalchemy as sa


revision = "0004_notification_outbox"
down_revision = "0003_admin_users"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "notification_jobs",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("reservation_id", sa.Integer(), sa.ForeignKey("reservations.id", ondelete="CASCADE"), nullable=False),
        sa.Column("kind", sa.String(length=32), nullable=False),
        sa.Column("status", sa.String(length=20), nullable=False),
        sa.Column("dedupe_key", sa.String(length=80), nullable=False),
        sa.Column("attempts", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("run_after", sa.DateTime(timezone=True), nullable=False),
        sa.Column("sent_at", sa.DateTime(timezone=True)),
        sa.Column("last_error", sa.Text()),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.UniqueConstraint("dedupe_key"),
    )
    op.create_index("ix_notification_jobs_reservation_id", "notification_jobs", ["reservation_id"])
    op.create_index("ix_notification_jobs_dispatch", "notification_jobs", ["status", "run_after"])


def downgrade() -> None:
    op.drop_table("notification_jobs")
