from __future__ import annotations

from datetime import time

from sqlalchemy import select
from sqlalchemy.orm import Session

from .dining_table import DiningTable, TableSection, TableShape
from .opening_hours import OpeningHours
from .restaurant import Restaurant


DEFAULT_TABLES = (
    ("Table 01", 2, TableSection.WINDOW, 18.0, 20.0, TableShape.ROUND, True),
    ("Table 02", 2, TableSection.MAIN_DINING, 42.0, 24.0, TableShape.ROUND, False),
    ("Table 03", 4, TableSection.MAIN_DINING, 64.0, 24.0, TableShape.ROUND, False),
    ("Table 04", 4, TableSection.WINDOW, 18.0, 50.0, TableShape.SQUARE, True),
    ("Table 05", 4, TableSection.MAIN_DINING, 48.0, 52.0, TableShape.SQUARE, False),
    ("Table 06", 6, TableSection.MAIN_DINING, 73.0, 54.0, TableShape.RECTANGLE, False),
    ("Table 07", 8, TableSection.PRIVATE, 70.0, 80.0, TableShape.RECTANGLE, True),
    ("Bar 01", 2, TableSection.BAR, 30.0, 82.0, TableShape.BAR, False),
)


def seed_restaurant_domain(session: Session) -> Restaurant:
    restaurant = session.scalar(select(Restaurant).where(Restaurant.name == "The Bower"))
    if restaurant is None:
        restaurant = Restaurant(name="The Bower", timezone="Asia/Kolkata", currency_code="INR")
        session.add(restaurant)
        session.flush()

    existing_tables = session.scalar(
        select(DiningTable.id).where(DiningTable.restaurant_id == restaurant.id).limit(1)
    )
    if existing_tables is None:
        session.add_all(
            DiningTable(
                restaurant_id=restaurant.id,
                display_name=name,
                capacity=capacity,
                section=section,
                x_position=x_position,
                y_position=y_position,
                shape=shape,
                accessible=accessible,
            )
            for name, capacity, section, x_position, y_position, shape, accessible in DEFAULT_TABLES
        )

    existing_hours = session.scalar(
        select(OpeningHours.id).where(OpeningHours.restaurant_id == restaurant.id).limit(1)
    )
    if existing_hours is None:
        for day_of_week in range(1, 7):
            session.add_all(
                (
                    OpeningHours(
                        restaurant_id=restaurant.id,
                        day_of_week=day_of_week,
                        opens_at=time(12, 0),
                        closes_at=time(15, 0),
                        last_seating_at=time(13, 30),
                    ),
                    OpeningHours(
                        restaurant_id=restaurant.id,
                        day_of_week=day_of_week,
                        opens_at=time(18, 0),
                        closes_at=time(23, 0),
                        last_seating_at=time(21, 30),
                    ),
                )
            )

    session.commit()
    return restaurant
