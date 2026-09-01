# The Bower

> **A quiet-luxury restaurant experience on the surface.
> A concurrency-safe reservation and operations system underneath.**

**The Bower** is a full-stack restaurant platform built with Flask, SQLAlchemy, Alembic, Tailwind CSS, modern browser tooling, and a deliberately restrained editorial design system.

What begins as a premium restaurant website extends into a real operational product: live table availability, transactional reservations, concurrency protection, staff administration, secure authentication, reservation lifecycle tracking, asynchronous notifications, accessibility, browser automation, and production deployment.

The goal is not to make a restaurant website look complicated.

The goal is to make the complexity disappear.

---

## ✦ Experience

The customer-facing interface follows a **quiet-luxury** visual language:

* editorial composition
* warm cream, bottle-green, brass, and burgundy palette
* restrained typography and whitespace
* responsive imagery
* deliberate motion instead of constant animation
* first-session wax-seal reveal
* context-aware candle-glow cursor
* accessible reduced-motion fallbacks
* touch, keyboard, and pointer support

Underneath that interface is a real reservation system designed around consistency, failure handling, and operational control.

---

# System at a glance

```text
                            ┌──────────────────────┐
                            │      Customer        │
                            │  Restaurant Website  │
                            └──────────┬───────────┘
                                       │
                         availability / reservation
                                       │
                                       ▼
                            ┌──────────────────────┐
                            │      Flask App       │
                            │                      │
                            │ Routes + Services    │
                            └───────┬───────┬──────┘
                                    │       │
                          booking   │       │ notification
                          domain    │       │ outbox
                                    ▼       ▼
                         ┌──────────────┐  ┌───────────────┐
                         │  SQLAlchemy  │  │ Notification  │
                         │   + Alembic  │  │    Worker     │
                         └──────┬───────┘  └───────┬───────┘
                                │                  │
                                ▼                  ▼
                         ┌──────────────┐     SMTP Provider
                         │   Database   │
                         │              │
                         │ Reservations │
                         │ Tables       │
                         │ Events       │
                         │ Users        │
                         └──────────────┘
```

---

# Core capabilities

## Reservation engine

The reservation experience is backed by server-side availability logic rather than browser-generated assumptions.

The system evaluates:

* restaurant opening periods
* final seating times
* special closures
* dining-table capacity
* table activation state
* existing reservations
* seating duration
* reset buffers between bookings
* requested party size

The booking rules live in:

```text
services/availability.py
```

and are centralized through `AvailabilitySettings`.

Current defaults:

```text
Slot interval       15 minutes
Reset buffer        15 minutes
Seating duration    90–135 minutes depending on party size
```

The browser is never treated as the source of truth.

Availability is validated again when a reservation is submitted.

---

## Reservation API

The public JSON API exposes:

```http
GET /api/availability?date=YYYY-MM-DD&partySize=N

POST /api/reservations

GET /api/reservations/<confirmation-code>

POST /api/reservations/<confirmation-code>/cancel
```

Reservation cancellation requires the booking email and is designed to be idempotent.

Cancelling a reservation also releases its occupied interval claims.

---

# Concurrency-safe booking

A restaurant reservation system has a deceptively simple race condition:

```text
Guest A sees Table 4 available
Guest B sees Table 4 available

        ↓

both attempt to reserve it
```

The Bower does not rely on frontend availability state to prevent this.

Reservation creation revalidates availability inside the database write transaction.

Every occupied 15-minute interval is claimed through a unique table/time record.

Conceptually:

```text
Guest A ─────┐
             │
             ├──► same table / same time
             │
Guest B ─────┘

                    │
                    ▼
              database transaction
                    │
              ┌─────┴─────┐
              │           │
              ▼           ▼
          A succeeds   B conflicts

              │           │
              ▼           ▼
          CONFIRMED    retry / choose
                      another slot
```

SQLite uses:

```text
BEGIN IMMEDIATE
```

to serialize booking writes.

Databases supporting row-level locking use:

```sql
SELECT ... FOR UPDATE
```

The result is simple:

> Two simultaneous requests cannot both confirm the same table for the same occupied interval.

---

# Reservation domain

The project uses SQLAlchemy for persistence and Alembic for schema evolution.

Database changes are migration-driven rather than being silently inferred at application startup.

After changing a model intentionally:

```bash
flask --app app db migrate -m "description"
```

Review the generated migration.

Then apply it:

```bash
flask --app app db upgrade
```

The reservation domain tracks operational state rather than treating a booking as a single static form submission.

Reservation lifecycle data and operational events remain available to the staff interface.

---

# Staff operations

The restaurant operations desk lives at:

```text
/admin
```

The admin application is intentionally more functional than the customer-facing experience.

## STAFF

Staff accounts can:

* inspect reservations
* modify reservation details
* manage reservation lifecycle states
* review booking history
* monitor notification delivery

## ADMIN

Administrators can additionally:

* manage dining tables
* manage opening periods
* manage restaurant closures
* manage staff access

The customer experience and operational experience are intentionally separated.

The public website optimizes for atmosphere.

The admin interface optimizes for clarity.

---

# Authentication & security

Admin authentication is backed by server-side security controls rather than simply hiding `/admin`.

The current implementation includes:

* **scrypt password hashing**
* server-signed sessions
* session expiration
* `HttpOnly` cookies
* `SameSite` cookie configuration
* production-only `Secure` cookies
* CSRF protection on every state-changing form
* temporary account lock after five failed sign-in attempts
* role-aware STAFF / ADMIN authorization

Create the first administrator interactively:

```bash
flask --app app create-admin
```

For non-interactive deployment, provide:

```text
ADMIN_BOOTSTRAP_EMAIL
ADMIN_BOOTSTRAP_PASSWORD
```

`ADMIN_BOOTSTRAP_PASSWORD` must contain at least 12 characters.

The `seed-domain` startup command creates the administrator only when the configured email does not already exist.

Plaintext credentials are never persisted.

Once the account exists on persistent infrastructure, remove the bootstrap password from the production environment.

---

# Notification architecture

Reservation confirmation should not fail simply because an email provider is unavailable.

The Bower therefore separates:

```text
booking success
```

from:

```text
notification delivery
```

The system uses a **database-backed notification outbox**.

```text
Reservation transaction
        │
        ▼
Database commit
        │
        ▼
Notification job
        │
        ▼
Background delivery
        │
        ├── SUCCESS
        │
        └── RETRY_PENDING
```

A provider outage never rolls back a confirmed reservation.

Failed deliveries move to:

```text
RETRY_PENDING
```

and use bounded exponential backoff.

The staff booking history exposes:

* delivery state
* retry count

Supported notification flows include:

* reservation confirmation
* cancellation confirmation
* 24-hour reservation reminder

---

## Development delivery mode

The default is intentionally safe:

```text
NOTIFICATION_DELIVERY_MODE=log
```

Emails are logged instead of delivered.

To enable SMTP delivery:

```text
NOTIFICATION_DELIVERY_MODE=smtp
SMTP_HOST=
SMTP_PORT=
NOTIFICATION_FROM_EMAIL=
SMTP_USERNAME=
SMTP_PASSWORD=
```

Username and password are optional when the SMTP provider does not require them.

Notification maintenance commands:

```bash
flask --app app enqueue-reminders
```

```bash
flask --app app process-notifications --limit 25
```

---

# Motion system

The visual system uses motion as atmosphere rather than decoration.

## Wax-seal opening

The first-session loader doubles as a restrained invitation-style reveal.

It:

* appears only on the first page load of a browser session
* releases directly into the hero
* does not repeatedly interrupt navigation
* becomes near-immediate when reduced motion is requested

---

## Candle cursor

The desktop cursor adapts inside sections marked:

```html
data-cursor-theme="candle"
```

Within those sections it develops a subtle warm candle-like glow.

The effect is disabled for:

* touch input
* reduced-motion users

Where supported, the desktop cursor uses:

```css
mix-blend-mode: difference;
```

with an opaque branded fallback where browser behavior differs.

The cursor is decorative only.

No interaction depends on it.

---

# Accessibility

Accessibility is treated as a product constraint rather than a final QA checkbox.

The experience preserves:

* keyboard navigation
* visible focus states
* semantic landmarks
* labelled forms
* live status regions
* touch-friendly menu interactions
* reduced-motion behavior
* accessible reservation controls

The printable experience intentionally removes the decorative shell and reduces the site to the menu.

---

# Responsive image pipeline

Flask does not provide automatic image optimization in the way some frontend frameworks do, so The Bower includes its own deterministic asset build.

Source PNG files remain untouched.

The build generates:

* responsive WebP variants
* production-ready image assets
* `static/img/og-bower.jpg`

The image pipeline is deterministic and safe to rerun.

---

# Quality engineering

The project includes both backend and browser-level verification.

Run the Python suite:

```bash
python -m pytest -q
```

Run browser tests:

```bash
npm run test:e2e
```

Install Playwright browsers once:

```bash
npm run playwright:install
```

The Playwright suite uses an isolated, seeded SQLite database.

Coverage includes:

* complete customer reservation lifecycle
* admin reservation lifecycle
* simultaneous scarce-table contention
* automated accessibility checks
* mobile layout
* Chromium rendering
* Firefox rendering
* WebKit rendering

Generated reports and traces remain inside ignored local testing directories.

---

# Performance

The Phase I local desktop audit measured:

```text
LCP             202 ms
CLS             0.00

Best Practices  100
SEO             100
```

Earlier Lighthouse contrast findings were corrected and are now enforced through the full axe accessibility scan.

These are **local laboratory measurements**, not production guarantees.

Production performance should still be monitored independently, particularly because Render's free service may require a cold start after idle spin-down.

---

# Local development

## Requirements

You need:

* Python
* Node.js / npm
* a Python virtual environment
* Playwright browser binaries for E2E testing

---

## 1. Create a virtual environment

```bash
python -m venv .venv
```

Activate it using the appropriate command for your operating system.

---

## 2. Install Python dependencies

```bash
python -m pip install -r requirements-dev.txt
```

---

## 3. Install frontend dependencies

```bash
npm ci
```

---

## 4. Apply database migrations

```bash
flask --app app db upgrade
```

---

## 5. Seed restaurant data

```bash
flask --app app seed-domain
```

This seeds:

* restaurant configuration
* opening periods
* dining tables

---

## 6. Build production assets

```bash
npm run build
```

This generates:

* responsive image variants
* stylesheet assets
* browser bundles

---

## 7. Start Flask

```bash
python app.py
```

Then open:

```text
http://127.0.0.1:5000
```

---

# Production deployment

The repository includes:

```text
render.yaml
```

for Render deployment.

The blueprint handles:

```text
Python dependencies
        +
frontend dependencies
        ↓
asset build
        ↓
Alembic migrations
        ↓
domain seed
        ↓
Gunicorn
        ↓
Flask application
```

Render automatically provides:

```text
RENDER_EXTERNAL_URL
```

When deploying somewhere else, configure:

```text
PUBLIC_BASE_URL
```

with the canonical HTTPS origin.

Every production environment must also contain a strong:

```text
SECRET_KEY
```

---

# Important persistence note

The current free-tier Render blueprint stores SQLite at:

```text
/tmp/the_bower.db
```

That filesystem is **ephemeral**.

Therefore:

> Reservations and other database changes can disappear when the free service restarts or redeploys.

This deployment mode is suitable for:

* portfolio demonstrations
* ephemeral environments
* automated testing
* temporary previews

It is **not** suitable for a real restaurant.

For persistent production data, use either:

```text
persistent disk
```

or preferably:

```text
managed production database
```

before treating the application as a real operational system.

---

# Environment configuration

Typical production configuration includes:

```env
SECRET_KEY=

PUBLIC_BASE_URL=

ADMIN_BOOTSTRAP_EMAIL=
ADMIN_BOOTSTRAP_PASSWORD=

NOTIFICATION_DELIVERY_MODE=

SMTP_HOST=
SMTP_PORT=
SMTP_USERNAME=
SMTP_PASSWORD=
NOTIFICATION_FROM_EMAIL=
```

Never commit real secrets.

Use environment variables in production and keep local secrets outside source control.

---

# Project decisions

Several design choices are deliberate rather than accidental.

## Restaurant identity

**The Bower**

The name was inherited from the original project folder and became the restaurant identity.

---

## Menu

Menu content is structured in:

```text
static/data/menu.json
```

and is ready for Jinja-driven rendering.

---

## Visit section

The Visit section intentionally uses restrained text rather than an embedded map.

The design prioritizes editorial calm over adding another interactive element simply because one is available.

---

## Philosophy section

The Philosophy section remains because it provides the site's one deliberate bottle-green visual transition.

It is a single high-contrast beat rather than a repeated motif.

---

## Press

There is no fabricated press carousel.

A press strip will only be introduced when genuine publication mentions exist.

---

## Photography

The Phase 1 photography grade and abstract texture crops are complete.

Asset usage rules are documented in:

```text
static/data/README.md
```

---

# Engineering philosophy

The Bower is built around a few constraints:

### The browser is not the source of truth.

Availability must be verified by the server.

### A booking and an email are different transactions.

Email failure must not destroy a valid reservation.

### Beautiful interfaces still need failure states.

Loading, contention, cancellation, authentication, and provider failure are part of the product.

### Motion should reinforce identity.

Animation exists because it belongs to the restaurant's visual language—not because an animation library is installed.

### Accessibility is part of the interaction model.

Keyboard, touch, pointer, reduced motion, and semantic structure are designed together.

### Production claims should be honest.

Local Lighthouse performance is reported as local performance.

Ephemeral SQLite is described as ephemeral.

Simulated/logged notifications are described as simulated/logged notifications.

No infrastructure capability is implied unless the project actually provides it.

---

# Why The Bower exists

A restaurant website is easy to make visually attractive.

A restaurant system becomes more interesting when two people try to reserve the same table, an email provider goes offline, a member of staff needs to change service hours, a guest cancels, a browser has reduced motion enabled, or production behaves differently from localhost.

**The Bower was built around those moments.**

The polished interface is what the guest sees.

The engineering underneath is what makes the experience trustworthy.
