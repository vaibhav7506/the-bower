from __future__ import annotations

import json
import os
import re
import sqlite3
from contextlib import closing
from datetime import timedelta
from pathlib import Path

import yaml
from flask import Flask, jsonify, render_template, request
from flask_compress import Compress


PROJECT_ROOT = Path(__file__).parent
MENU_PATH = PROJECT_ROOT / "static" / "data" / "menu.json"
AVAILABILITY_PATH = PROJECT_ROOT / "static" / "data" / "availability.yaml"
VERSIONED_ASSETS = (
    PROJECT_ROOT / "static" / "css" / "site.css",
    PROJECT_ROOT / "static" / "js" / "loader.js",
    PROJECT_ROOT / "static" / "js" / "site.js",
    PROJECT_ROOT / "static" / "js" / "bootstrap.js",
    PROJECT_ROOT / "static" / "js" / "motion.js",
    PROJECT_ROOT / "static" / "js" / "reservations.js",
)
EMAIL_PATTERN = re.compile(r"^[^\s@]+@[^\s@]+\.[^\s@]+$")


def initialize_database(database_path: Path) -> None:
    database_path.parent.mkdir(parents=True, exist_ok=True)
    with closing(sqlite3.connect(database_path)) as connection:
        connection.executescript(
            """
            CREATE TABLE IF NOT EXISTS newsletter_subscribers (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                email TEXT NOT NULL UNIQUE,
                created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
            );

            CREATE TABLE IF NOT EXISTS private_event_inquiries (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                name TEXT NOT NULL,
                email TEXT NOT NULL,
                event_date TEXT NOT NULL,
                party_size INTEGER NOT NULL,
                message TEXT NOT NULL,
                created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
            );
            """
        )
        connection.commit()


def create_app() -> Flask:
    app = Flask(__name__)
    database_path = Path(
        os.environ.get("DATABASE_PATH", str(Path(app.instance_path) / "the_bower.db"))
    )
    public_base_url = (
        os.environ.get("PUBLIC_BASE_URL")
        or os.environ.get("RENDER_EXTERNAL_URL")
        or "http://127.0.0.1:5000"
    ).rstrip("/")
    app.config.from_mapping(
        SECRET_KEY=os.environ.get("SECRET_KEY", "development-only-change-before-production"),
        DATABASE=database_path,
        PUBLIC_BASE_URL=public_base_url,
        SEND_FILE_MAX_AGE_DEFAULT=timedelta(days=30),
        COMPRESS_MIMETYPES=(
            "text/html",
            "text/css",
            "application/javascript",
            "application/json",
            "image/svg+xml",
        ),
    )
    Compress(app)
    initialize_database(app.config["DATABASE"])

    @app.context_processor
    def site_metadata() -> dict[str, object]:
        base_url = app.config["PUBLIC_BASE_URL"]
        asset_version = os.environ.get("ASSET_VERSION") or str(
            max(asset.stat().st_mtime_ns for asset in VERSIONED_ASSETS)
        )
        restaurant_schema = {
            "@context": "https://schema.org",
            "@type": "Restaurant",
            "name": "The Bower",
            "url": base_url,
            "image": f"{base_url}/static/img/og-bower.jpg",
            "description": "A quiet, seasonal dining room in Bengaluru.",
            "servesCuisine": ["Modern European", "Seasonal"],
            "priceRange": "₹₹₹",
            "email": "tables@thebower.example",
            "address": {
                "@type": "PostalAddress",
                "streetAddress": "12 Garden Lane, Richmond Town",
                "addressLocality": "Bengaluru",
                "postalCode": "560025",
                "addressCountry": "IN",
            },
            "openingHoursSpecification": [
                {
                    "@type": "OpeningHoursSpecification",
                    "dayOfWeek": ["Tuesday", "Wednesday", "Thursday", "Friday", "Saturday", "Sunday"],
                    "opens": "12:00",
                    "closes": "15:00",
                },
                {
                    "@type": "OpeningHoursSpecification",
                    "dayOfWeek": ["Tuesday", "Wednesday", "Thursday", "Friday", "Saturday", "Sunday"],
                    "opens": "18:00",
                    "closes": "23:00",
                },
            ],
        }
        return {
            "asset_version": asset_version,
            "public_base_url": base_url,
            "restaurant_schema": restaurant_schema,
        }

    @app.get("/")
    def home():
        menu = json.loads(MENU_PATH.read_text(encoding="utf-8"))
        availability = yaml.safe_load(AVAILABILITY_PATH.read_text(encoding="utf-8"))
        return render_template("index.html", menu=menu, availability=availability)

    @app.post("/api/newsletter")
    def newsletter_signup():
        payload = request.get_json(silent=True) or request.form
        email = str(payload.get("email", "")).strip().lower()

        if not EMAIL_PATTERN.fullmatch(email) or len(email) > 254:
            return jsonify(ok=False, message="Please enter a valid email address."), 400

        with closing(sqlite3.connect(app.config["DATABASE"])) as connection:
            cursor = connection.execute(
                "INSERT OR IGNORE INTO newsletter_subscribers (email) VALUES (?)",
                (email,),
            )
            connection.commit()

        if cursor.rowcount == 0:
            message = "You’re already on the list. We’ll be in touch quietly."
        else:
            message = "Thank you. Seasonal notes will arrive occasionally."

        return jsonify(ok=True, message=message)

    @app.post("/api/private-events")
    def private_event_inquiry():
        payload = request.get_json(silent=True) or request.form
        name = str(payload.get("name", "")).strip()
        email = str(payload.get("email", "")).strip().lower()
        event_date = str(payload.get("event_date", "")).strip()
        message = str(payload.get("message", "")).strip()

        try:
            party_size = int(payload.get("party_size", 0))
        except (TypeError, ValueError):
            party_size = 0

        if not name or len(name) > 120:
            return jsonify(ok=False, message="Please tell us your name."), 400
        if not EMAIL_PATTERN.fullmatch(email) or len(email) > 254:
            return jsonify(ok=False, message="Please enter a valid email address."), 400
        if not event_date:
            return jsonify(ok=False, message="Please choose a preferred date."), 400
        if not 1 <= party_size <= 200:
            return jsonify(ok=False, message="Party size must be between 1 and 200."), 400
        if not message or len(message) > 2000:
            return jsonify(ok=False, message="Please add a short note (up to 2,000 characters)."), 400

        with closing(sqlite3.connect(app.config["DATABASE"])) as connection:
            connection.execute(
                """
                INSERT INTO private_event_inquiries
                    (name, email, event_date, party_size, message)
                VALUES (?, ?, ?, ?, ?)
                """,
                (name, email, event_date, party_size, message),
            )
            connection.commit()

        return jsonify(
            ok=True,
            message="Thank you. Our private dining team will reply within two working days.",
        ), 201

    @app.errorhandler(404)
    def not_found(_error):
        return render_template("404.html"), 404

    return app


app = create_app()


if __name__ == "__main__":
    app.run(debug=True)
