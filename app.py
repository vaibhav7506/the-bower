from __future__ import annotations

import json
import os
import re
import click
from datetime import date
from pathlib import Path

from flask import Flask, current_app, jsonify, render_template, request
from flask_compress import Compress
from sqlalchemy import create_engine, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from config import Config, sqlite_uri
from extensions import db, login_manager, migrate
from models import NewsletterSubscriber, PrivateEventInquiry, User, UserRole
from models.seed import seed_restaurant_domain
from routes import admin, reservation_api
from services import NotificationService, process_due_notifications


PROJECT_ROOT = Path(__file__).parent
MENU_PATH = PROJECT_ROOT / "static" / "data" / "menu.json"
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
    """Create and seed an isolated database for development and tests."""
    database_path.parent.mkdir(parents=True, exist_ok=True)
    engine = create_engine(sqlite_uri(database_path))
    db.metadata.create_all(bind=engine)
    with Session(engine) as session:
        seed_restaurant_domain(session)
    engine.dispose()


def create_app(test_config: dict[str, object] | None = None) -> Flask:
    app = Flask(__name__)
    app.config.from_object(Config)
    if test_config:
        app.config.update(test_config)
    if app.testing and (not test_config or "NOTIFICATION_AUTO_DISPATCH" not in test_config):
        app.config["NOTIFICATION_AUTO_DISPATCH"] = False

    db.init_app(app)
    migrate.init_app(app, db)
    login_manager.init_app(app)
    Compress(app)
    app.register_blueprint(reservation_api)
    app.register_blueprint(admin)

    @app.after_request
    def apply_security_headers(response):
        response.headers.setdefault("X-Content-Type-Options", "nosniff")
        response.headers.setdefault("Referrer-Policy", "strict-origin-when-cross-origin")
        response.headers.setdefault(
            "Permissions-Policy",
            "camera=(), microphone=(), geolocation=(), payment=()",
        )
        response.headers.setdefault("X-Frame-Options", "SAMEORIGIN")
        response.headers.setdefault(
            "Content-Security-Policy",
            "default-src 'self'; base-uri 'self'; form-action 'self'; frame-ancestors 'self'; "
            "img-src 'self' data:; font-src 'self'; style-src 'self' 'unsafe-inline'; "
            "script-src 'self' 'unsafe-inline'; connect-src 'self'",
        )
        if request.is_secure:
            response.headers.setdefault(
                "Strict-Transport-Security",
                "max-age=31536000; includeSubDomains",
            )
        return response

    @login_manager.user_loader
    def load_user(user_id: str):
        return db.session.get(User, int(user_id)) if user_id.isdigit() else None

    @app.cli.command("seed-domain")
    def seed_domain_command() -> None:
        seed_restaurant_domain(db.session)
        bootstrap_email = os.environ.get("ADMIN_BOOTSTRAP_EMAIL", "").strip().lower()
        bootstrap_password = os.environ.get("ADMIN_BOOTSTRAP_PASSWORD", "")
        if bootstrap_email and bootstrap_password:
            existing_admin = db.session.scalar(select(User).where(User.email == bootstrap_email))
            if existing_admin is None:
                user = User(
                    name=os.environ.get("ADMIN_BOOTSTRAP_NAME", "Restaurant Admin").strip(),
                    email=bootstrap_email,
                    role=UserRole.ADMIN,
                )
                try:
                    user.set_password(bootstrap_password)
                except ValueError as error:
                    raise click.ClickException(str(error)) from error
                db.session.add(user)
                db.session.commit()
                click.echo(f"Bootstrapped admin account for {bootstrap_email}.")
        print("The Bower restaurant domain is ready.")

    @app.cli.command("create-admin")
    @click.option("--email", prompt=True)
    @click.option("--name", prompt=True)
    @click.password_option(confirmation_prompt=True)
    def create_admin_command(email: str, name: str, password: str) -> None:
        normalized_email = email.strip().lower()
        existing = db.session.scalar(select(User).where(User.email == normalized_email))
        if existing is not None:
            raise click.ClickException("An account with that email already exists.")
        user = User(name=name.strip(), email=normalized_email, role=UserRole.ADMIN)
        try:
            user.set_password(password)
        except ValueError as error:
            raise click.ClickException(str(error)) from error
        db.session.add(user)
        db.session.commit()
        click.echo(f"Admin account created for {normalized_email}.")

    @app.cli.command("enqueue-reminders")
    def enqueue_reminders_command() -> None:
        job_ids = NotificationService(db.session).enqueue_due_reminders()
        click.echo(f"Queued {len(job_ids)} reservation reminder(s).")

    @app.cli.command("process-notifications")
    @click.option("--limit", type=click.IntRange(1, 250), default=25, show_default=True)
    def process_notifications_command(limit: int) -> None:
        processed = process_due_notifications(limit)
        click.echo(f"Processed {processed} notification job(s).")

    @app.context_processor
    def site_metadata() -> dict[str, object]:
        base_url = current_app.config["PUBLIC_BASE_URL"]
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
                    "dayOfWeek": [
                        "Tuesday",
                        "Wednesday",
                        "Thursday",
                        "Friday",
                        "Saturday",
                        "Sunday",
                    ],
                    "opens": "12:00",
                    "closes": "15:00",
                },
                {
                    "@type": "OpeningHoursSpecification",
                    "dayOfWeek": [
                        "Tuesday",
                        "Wednesday",
                        "Thursday",
                        "Friday",
                        "Saturday",
                        "Sunday",
                    ],
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
        return render_template("index.html", menu=menu)

    @app.post("/api/newsletter")
    def newsletter_signup():
        payload = request.get_json(silent=True) or request.form
        email = str(payload.get("email", "")).strip().lower()

        if not EMAIL_PATTERN.fullmatch(email) or len(email) > 254:
            return jsonify(ok=False, message="Please enter a valid email address."), 400

        existing_subscriber = db.session.scalar(
            select(NewsletterSubscriber).where(NewsletterSubscriber.email == email)
        )
        if existing_subscriber is not None:
            message = "You’re already on the list. We’ll be in touch quietly."
        else:
            db.session.add(NewsletterSubscriber(email=email))
            try:
                db.session.commit()
                message = "Thank you. Seasonal notes will arrive occasionally."
            except IntegrityError:
                db.session.rollback()
                message = "You’re already on the list. We’ll be in touch quietly."

        return jsonify(ok=True, message=message)

    @app.post("/api/private-events")
    def private_event_inquiry():
        payload = request.get_json(silent=True) or request.form
        name = str(payload.get("name", "")).strip()
        email = str(payload.get("email", "")).strip().lower()
        event_date_value = str(payload.get("event_date", "")).strip()
        message = str(payload.get("message", "")).strip()

        try:
            party_size = int(payload.get("party_size", 0))
        except (TypeError, ValueError):
            party_size = 0

        if not name or len(name) > 120:
            return jsonify(ok=False, message="Please tell us your name."), 400
        if not EMAIL_PATTERN.fullmatch(email) or len(email) > 254:
            return jsonify(ok=False, message="Please enter a valid email address."), 400
        try:
            event_date = date.fromisoformat(event_date_value)
        except ValueError:
            return jsonify(ok=False, message="Please choose a preferred date."), 400
        if not 1 <= party_size <= 200:
            return jsonify(ok=False, message="Party size must be between 1 and 200."), 400
        if not message or len(message) > 2000:
            return jsonify(
                ok=False,
                message="Please add a short note (up to 2,000 characters).",
            ), 400

        db.session.add(
            PrivateEventInquiry(
                name=name,
                email=email,
                event_date=event_date,
                party_size=party_size,
                message=message,
            )
        )
        db.session.commit()

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
