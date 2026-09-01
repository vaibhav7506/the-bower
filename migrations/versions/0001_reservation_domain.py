"""Create the restaurant reservation domain.

Revision ID: 0001_reservation_domain
Revises:
"""
from __future__ import annotations

from alembic import op
import sqlalchemy as sa


revision = "0001_reservation_domain"
down_revision = None
branch_labels = None
depends_on = None


def has_table(table_name: str) -> bool:
    return table_name in sa.inspect(op.get_bind()).get_table_names()


def timestamp_columns() -> tuple[sa.Column, sa.Column]:
    return (
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("CURRENT_TIMESTAMP"),
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("CURRENT_TIMESTAMP"),
        ),
    )


def upgrade() -> None:
    if not has_table("newsletter_subscribers"):
        op.create_table(
            "newsletter_subscribers",
            sa.Column("id", sa.Integer(), primary_key=True),
            sa.Column("email", sa.String(length=254), nullable=False, unique=True),
            sa.Column(
                "created_at",
                sa.DateTime(timezone=True),
                nullable=False,
                server_default=sa.text("CURRENT_TIMESTAMP"),
            ),
        )

    if not has_table("private_event_inquiries"):
        op.create_table(
            "private_event_inquiries",
            sa.Column("id", sa.Integer(), primary_key=True),
            sa.Column("name", sa.String(length=120), nullable=False),
            sa.Column("email", sa.String(length=254), nullable=False),
            sa.Column("event_date", sa.Date(), nullable=False),
            sa.Column("party_size", sa.Integer(), nullable=False),
            sa.Column("message", sa.Text(), nullable=False),
            sa.Column(
                "created_at",
                sa.DateTime(timezone=True),
                nullable=False,
                server_default=sa.text("CURRENT_TIMESTAMP"),
            ),
        )

    if not has_table("restaurants"):
        op.create_table(
            "restaurants",
            sa.Column("id", sa.Integer(), primary_key=True),
            sa.Column("name", sa.String(length=120), nullable=False),
            sa.Column("timezone", sa.String(length=64), nullable=False),
            sa.Column("currency_code", sa.String(length=3), nullable=False),
            *timestamp_columns(),
        )

    if not has_table("customers"):
        op.create_table(
            "customers",
            sa.Column("id", sa.Integer(), primary_key=True),
            sa.Column("name", sa.String(length=120), nullable=False),
            sa.Column("email", sa.String(length=254), nullable=False),
            sa.Column("phone", sa.String(length=32), nullable=True),
            *timestamp_columns(),
        )
        op.create_index("ix_customers_email", "customers", ["email"])
        op.create_index("ix_customers_phone", "customers", ["phone"])

    if not has_table("dining_tables"):
        op.create_table(
            "dining_tables",
            sa.Column("id", sa.Integer(), primary_key=True),
            sa.Column(
                "restaurant_id",
                sa.Integer(),
                sa.ForeignKey("restaurants.id", ondelete="CASCADE"),
                nullable=False,
            ),
            sa.Column("display_name", sa.String(length=40), nullable=False),
            sa.Column("capacity", sa.Integer(), nullable=False),
            sa.Column("section", sa.String(length=24), nullable=False),
            sa.Column("x_position", sa.Float(), nullable=False),
            sa.Column("y_position", sa.Float(), nullable=False),
            sa.Column("shape", sa.String(length=16), nullable=False),
            sa.Column("active", sa.Boolean(), nullable=False, server_default=sa.true()),
            sa.Column("accessible", sa.Boolean(), nullable=False, server_default=sa.false()),
            *timestamp_columns(),
            sa.CheckConstraint("capacity > 0", name="ck_table_capacity_positive"),
            sa.CheckConstraint(
                "x_position >= 0 AND x_position <= 100",
                name="ck_table_x_position",
            ),
            sa.CheckConstraint(
                "y_position >= 0 AND y_position <= 100",
                name="ck_table_y_position",
            ),
            sa.UniqueConstraint(
                "restaurant_id",
                "display_name",
                name="uq_table_restaurant_name",
            ),
        )
        op.create_index(
            "ix_dining_tables_restaurant_active",
            "dining_tables",
            ["restaurant_id", "active"],
        )

    if not has_table("opening_hours"):
        op.create_table(
            "opening_hours",
            sa.Column("id", sa.Integer(), primary_key=True),
            sa.Column(
                "restaurant_id",
                sa.Integer(),
                sa.ForeignKey("restaurants.id", ondelete="CASCADE"),
                nullable=False,
            ),
            sa.Column("day_of_week", sa.Integer(), nullable=False),
            sa.Column("opens_at", sa.Time(), nullable=False),
            sa.Column("closes_at", sa.Time(), nullable=False),
            sa.Column("last_seating_at", sa.Time(), nullable=False),
            sa.Column("active", sa.Boolean(), nullable=False, server_default=sa.true()),
            *timestamp_columns(),
            sa.CheckConstraint(
                "day_of_week >= 0 AND day_of_week <= 6",
                name="ck_opening_hours_day",
            ),
            sa.CheckConstraint("opens_at < closes_at", name="ck_opening_hours_range"),
            sa.CheckConstraint(
                "last_seating_at >= opens_at AND last_seating_at <= closes_at",
                name="ck_opening_hours_last_seating",
            ),
            sa.UniqueConstraint(
                "restaurant_id",
                "day_of_week",
                "opens_at",
                name="uq_opening_hours_service",
            ),
        )
        op.create_index(
            "ix_opening_hours_lookup",
            "opening_hours",
            ["restaurant_id", "day_of_week", "active"],
        )

    if not has_table("special_closures"):
        op.create_table(
            "special_closures",
            sa.Column("id", sa.Integer(), primary_key=True),
            sa.Column(
                "restaurant_id",
                sa.Integer(),
                sa.ForeignKey("restaurants.id", ondelete="CASCADE"),
                nullable=False,
            ),
            sa.Column("date", sa.Date(), nullable=False),
            sa.Column("reason", sa.String(length=240), nullable=False),
            sa.Column("full_day", sa.Boolean(), nullable=False, server_default=sa.true()),
            sa.Column("starts_at", sa.Time(), nullable=True),
            sa.Column("ends_at", sa.Time(), nullable=True),
            *timestamp_columns(),
            sa.CheckConstraint(
                ""full_day IS TRUE OR (starts_at IS NOT NULL AND ends_at IS NOT NULL)"",
                name="ck_special_closure_window",
            ),
            sa.CheckConstraint(
                "starts_at IS NULL OR ends_at IS NULL OR starts_at < ends_at",
                name="ck_special_closure_range",
            ),
        )
        op.create_index(
            "ix_special_closures_lookup",
            "special_closures",
            ["restaurant_id", "date"],
        )

    if not has_table("reservations"):
        op.create_table(
            "reservations",
            sa.Column("id", sa.Integer(), primary_key=True),
            sa.Column("confirmation_code", sa.String(length=16), nullable=False),
            sa.Column(
                "customer_id",
                sa.Integer(),
                sa.ForeignKey("customers.id", ondelete="RESTRICT"),
                nullable=False,
            ),
            sa.Column(
                "dining_table_id",
                sa.Integer(),
                sa.ForeignKey("dining_tables.id", ondelete="RESTRICT"),
                nullable=True,
            ),
            sa.Column("customer_name", sa.String(length=120), nullable=False),
            sa.Column("email", sa.String(length=254), nullable=False),
            sa.Column("phone", sa.String(length=32), nullable=True),
            sa.Column("party_size", sa.Integer(), nullable=False),
            sa.Column("starts_at", sa.DateTime(timezone=True), nullable=False),
            sa.Column("ends_at", sa.DateTime(timezone=True), nullable=False),
            sa.Column("status", sa.String(length=16), nullable=False),
            sa.Column("special_requests", sa.Text(), nullable=True),
            *timestamp_columns(),
            sa.CheckConstraint(
                "party_size > 0",
                name="ck_reservation_party_size_positive",
            ),
            sa.CheckConstraint(
                "starts_at < ends_at",
                name="ck_reservation_time_range",
            ),
        )
        op.create_index(
            "ix_reservations_confirmation_code",
            "reservations",
            ["confirmation_code"],
            unique=True,
        )
        op.create_index(
            "ix_reservations_dining_table_id",
            "reservations",
            ["dining_table_id"],
        )
        op.create_index(
            "ix_reservations_service_window",
            "reservations",
            ["starts_at", "ends_at", "status"],
        )
        op.create_index(
            "ix_reservations_table_window",
            "reservations",
            ["dining_table_id", "starts_at", "ends_at", "status"],
        )

    if not has_table("reservation_events"):
        op.create_table(
            "reservation_events",
            sa.Column("id", sa.Integer(), primary_key=True),
            sa.Column(
                "reservation_id",
                sa.Integer(),
                sa.ForeignKey("reservations.id", ondelete="CASCADE"),
                nullable=False,
            ),
            sa.Column("event_type", sa.String(length=24), nullable=False),
            sa.Column("actor_type", sa.String(length=16), nullable=False),
            sa.Column("actor_reference", sa.String(length=120), nullable=True),
            sa.Column("metadata", sa.JSON(), nullable=False),
            sa.Column(
                "occurred_at",
                sa.DateTime(timezone=True),
                nullable=False,
                server_default=sa.text("CURRENT_TIMESTAMP"),
            ),
        )
        op.create_index(
            "ix_reservation_events_history",
            "reservation_events",
            ["reservation_id", "occurred_at"],
        )


def downgrade() -> None:
    for table_name in (
        "reservation_events",
        "reservations",
        "special_closures",
        "opening_hours",
        "dining_tables",
        "customers",
        "restaurants",
        "private_event_inquiries",
        "newsletter_subscribers",
    ):
        if has_table(table_name):
            op.drop_table(table_name)
