from __future__ import annotations

import sqlite3
import tempfile
import unittest
from contextlib import closing
from pathlib import Path

from app import create_app, initialize_database
from config import sqlite_uri
from extensions import db


class TheBowerAppTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temp_directory = tempfile.TemporaryDirectory()
        self.database_path = Path(self.temp_directory.name) / "test.db"
        initialize_database(self.database_path)
        self.app = create_app(
            {
                "TESTING": True,
                "SQLALCHEMY_DATABASE_URI": sqlite_uri(self.database_path),
            }
        )
        self.client = self.app.test_client()

    def tearDown(self) -> None:
        with self.app.app_context():
            db.session.remove()
            db.engine.dispose()
        self.temp_directory.cleanup()

    def test_home_renders_menu_and_reservation_data(self) -> None:
        response = self.client.get("/")
        favicon = self.client.get("/static/favicon.svg")
        page = response.get_data(as_text=True)

        self.assertEqual(response.status_code, 200)
        self.assertEqual(favicon.status_code, 200)
        self.assertEqual(favicon.mimetype, "image/svg+xml")
        favicon.close()
        self.assertEqual(page.count("data-flip-card"), 8)
        self.assertNotIn('id="availability-data"', page)
        self.assertIn("data-reservation-form", page)
        self.assertIn("data-confirmation-code", page)
        self.assertIn("data-newsletter-form", page)
        self.assertIn("data-event-dialog", page)
        self.assertIn("hero-graded-480.webp 480w", page)
        self.assertIn('fetchpriority="high"', page)
        self.assertIn("data-loader-copy", page)
        self.assertIn("data-loader-announcement", page)
        self.assertIn("js/loader.js", page)
        self.assertIn("js/bootstrap.js", page)
        self.assertIn('data-asset-version="', page)
        self.assertRegex(page, r"css/site\.css\?v=\d+")
        self.assertEqual(page.count('class="menu-preview-card__image"'), 8)
        self.assertEqual(page.count("-320.webp 320w"), 8)
        self.assertIn('name="viewport" content="width=device-width, initial-scale=1"', page)
        self.assertIn('rel="icon" href="/static/favicon.svg" type="image/svg+xml"', page)
        self.assertIn('property="og:image"', page)
        self.assertIn('/static/img/og-bower.jpg', page)
        self.assertIn('type="application/ld+json"', page)
        self.assertIn('"@type": "Restaurant"', page)
        self.assertIn('class="skip-link" href="#main-content"', page)
        self.assertIn('id="main-content" tabindex="-1"', page)
        self.assertIn('data-reservation-status aria-live="polite"', page)

    def test_production_assets_and_error_page(self) -> None:
        social_image = self.client.get("/static/img/og-bower.jpg")
        responsive_hero = self.client.get("/static/img/hero-graded-480.webp")
        missing = self.client.get("/a-table-that-does-not-exist")

        self.assertEqual(social_image.status_code, 200)
        self.assertEqual(social_image.mimetype, "image/jpeg")
        self.assertIn("max-age=", social_image.headers["Cache-Control"])
        self.assertEqual(responsive_hero.status_code, 200)
        self.assertEqual(responsive_hero.mimetype, "image/webp")
        self.assertEqual(missing.status_code, 404)
        self.assertIn("This table", missing.get_data(as_text=True))
        self.assertIn("Return to The Bower", missing.get_data(as_text=True))

    def test_html_compression_is_enabled(self) -> None:
        response = self.client.get("/", headers={"Accept-Encoding": "gzip"})

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.headers.get("Content-Encoding"), "gzip")

    def test_newsletter_validates_and_deduplicates(self) -> None:
        invalid = self.client.post("/api/newsletter", json={"email": "not-an-email"})
        first = self.client.post("/api/newsletter", json={"email": "guest@example.com"})
        duplicate = self.client.post("/api/newsletter", json={"email": "guest@example.com"})

        self.assertEqual(invalid.status_code, 400)
        self.assertEqual(first.status_code, 200)
        self.assertEqual(duplicate.status_code, 200)

        with closing(sqlite3.connect(self.database_path)) as connection:
            count = connection.execute("SELECT COUNT(*) FROM newsletter_subscribers").fetchone()[0]
        self.assertEqual(count, 1)

    def test_private_event_inquiry_persists(self) -> None:
        response = self.client.post(
            "/api/private-events",
            json={
                "name": "A Guest",
                "email": "guest@example.com",
                "event_date": "2026-10-10",
                "party_size": 24,
                "message": "A quiet anniversary dinner.",
            },
        )

        self.assertEqual(response.status_code, 201)
        with closing(sqlite3.connect(self.database_path)) as connection:
            count = connection.execute("SELECT COUNT(*) FROM private_event_inquiries").fetchone()[0]
        self.assertEqual(count, 1)


if __name__ == "__main__":
    unittest.main()
