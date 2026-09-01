# The Bower

Flask foundation for a quiet-luxury restaurant portfolio site.

## Run locally

1. Create and activate a Python virtual environment.
2. Install Python dependencies: `python -m pip install -r requirements-dev.txt`
3. Install frontend dependencies: `npm ci`
4. Apply the database schema: `flask --app app db upgrade`
5. Seed the restaurant, opening hours, and dining tables: `flask --app app seed-domain`
6. Build responsive images, the stylesheet, and browser bundles: `npm run build`
7. Start Flask: `python app.py`

Visit `http://127.0.0.1:5000`.

## Production

`render.yaml` is the free-tier deployment blueprint. It installs both dependency sets,
runs the full asset build, applies Alembic migrations, seeds required restaurant data,
and serves Flask with Gunicorn. SQLite is stored at
`/tmp/the_bower.db`, so form submissions are temporary and can disappear whenever the
free service restarts or redeploys. For persistent production data, upgrade to a plan
with a persistent disk or connect the app to a managed database.

Set `PUBLIC_BASE_URL` to the canonical HTTPS origin when deploying somewhere other
than Render. Render supplies `RENDER_EXTERNAL_URL` automatically. Set a strong
`SECRET_KEY` in every production environment.

Run the verification suite with:

```text
pytest
```

The reservation domain is modeled with SQLAlchemy and versioned through Alembic. Run
`flask --app app db migrate -m "description"` after deliberate model changes, review
the generated migration, then apply it with `flask --app app db upgrade`.

The image build is deterministic and safe to rerun. Source PNG files remain in place;
generated WebP variants and `static/img/og-bower.jpg` are deployment assets.

## Accessibility and browser behavior

The site preserves keyboard operation, visible focus, semantic landmarks, labelled
forms, live status regions, touch-friendly menu cards, and reduced-motion behavior.
The desktop cursor uses `mix-blend-mode: difference` where supported and a branded
opaque fallback otherwise. The printable view reduces the experience to the menu.

## Phase 1 decisions

- Restaurant name: **The Bower** (taken from the project folder).
- The future menu is structured in `static/data/menu.json`, ready for a Jinja loop in Phase 5.
- The visit block will use the restrained text-only treatment, with no embedded map.
- The Philosophy section is retained for the one-time bottle-green transition in Phase 4.
- No press strip will be added unless genuine mentions are supplied.

The Phase 1 photo grade and abstract texture crops are complete. See `static/data/README.md` for the approved role of each asset.
