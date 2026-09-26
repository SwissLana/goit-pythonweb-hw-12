# Secure Contact Management REST API

An asynchronous FastAPI service for private contact collections with PostgreSQL, Redis caching, email verification, password recovery, role-based access, and rotating JWT access/refresh tokens.

## Live deployment

- Swagger documentation: https://secure-contact-api.onrender.com/docs
- Health check: https://secure-contact-api.onrender.com/health

The application is deployed on Render with PostgreSQL and a Redis-compatible Valkey cache. The free instance may require up to 50 seconds to wake after inactivity.

## Highlights

- Async FastAPI, SQLAlchemy 2, Psycopg 3, and Alembic
- Registration with normalized unique identities and Argon2 password hashing
- Email verification through SMTP or a safe development console backend
- Signed JWT access tokens with issuer, audience, purpose, expiry, and token IDs
- Rotating refresh tokens with replay prevention; only token digests are stored
- Redis-first current-user resolution with bounded TTL and database fallback
- Cache invalidation after profile, role, verification, and password changes
- One-time password-reset tokens with expiration and non-disclosing responses
- `user` and `admin` roles with explicit administrator dependencies
- Administrator-only avatar replacement through Cloudinary
- Owner-isolated contact CRUD, search, pagination, and upcoming birthdays
- CORS, `/me` rate limiting, health checks, and OpenAPI documentation
- Separate unit and integration test suites with an enforced coverage threshold
- Sphinx API documentation generated from application docstrings
- Docker Compose for the API, PostgreSQL, and Redis
- Render Blueprint for optional cloud deployment

## Architecture

```text
Client
  └── FastAPI routers
        ├── Pydantic schemas
        ├── security dependencies ── Redis user cache
        ├── repositories ────────── PostgreSQL
        └── services ────────────── SMTP / Cloudinary
```

Authentication reads `auth:user:<id>` from Redis before querying PostgreSQL. Cached documents contain only public profile and authorization fields - never password or token hashes. Redis failures fall back to PostgreSQL so authentication remains available.

Every contact query includes `owner_id`. Access to another user's identifier returns `404 Not Found`, avoiding both unauthorized modification and resource disclosure.

## Local setup with Docker Compose

Copy the example configuration:

```bash
cp .env.example .env
```

Generate a strong JWT signing key and put it in `JWT_SECRET_KEY`:

```bash
openssl rand -hex 32
```

Change `POSTGRES_PASSWORD` and update the local `DATABASE_URL` password to match. Never commit `.env`.

Start the complete stack:

```bash
docker compose up --build
```

Compose waits for PostgreSQL and Redis, applies all Alembic migrations, and starts the API.

- Swagger UI: <http://localhost:8000/docs>
- ReDoc: <http://localhost:8000/redoc>
- Health endpoint: <http://localhost:8000/health>

Stop the services while preserving PostgreSQL data:

```bash
docker compose down
```

## Local Python development

```bash
python3 -m venv .venv
source .venv/bin/activate
python -m pip install -r requirements-dev.txt
cp .env.example .env
docker compose up -d db redis
alembic upgrade head
uvicorn app.main:app --reload
```

On Windows PowerShell, activate the environment with
`.venv\Scripts\Activate.ps1`.

## Authentication lifecycle

1. Register with `POST /api/auth/register`.
2. Open the verification link delivered by the configured email backend.
3. Submit OAuth2 form fields `username` and `password` to `POST /api/auth/login`. The `username` field accepts a username or email address.
4. Send `Authorization: Bearer <access_token>` to protected routes.
5. Submit the refresh token to `POST /api/auth/refresh` before access-token expiry.
6. Replace the stored refresh token after every successful refresh. Replaying an older token returns `401 Unauthorized`.
7. Revoke the active refresh token with `POST /api/auth/logout`.

Only SHA-256 refresh-token digests are stored. Password resets clear the digest and increment `auth_version`, immediately invalidating every older access token.

## Password recovery

Request recovery with:

```http
POST /api/auth/password-reset/request
Content-Type: application/json

{"email": "ada@example.com"}
```

The endpoint intentionally returns the same `202 Accepted` response for existing and missing accounts. Verified users receive a high-entropy token that expires after the configured interval and works only once.

Confirm with `POST /api/auth/password-reset/confirm` using `token` and
`new_password`. A successful reset revokes refresh tokens, invalidates Redis, and rejects access tokens issued before the reset.

## Roles and the first administrator

Public registration always creates the safe `user` role. Promote the first trusted administrator from inside the running API container:

```bash
docker compose exec api python -m app.cli promote-admin --email admin@example.com
```

Administrators may change roles with `PATCH /api/users/{user_id}/role`. Only
administrators can use `PATCH /api/users/me/avatar`, as required by the final
assignment. Cache entries are invalidated whenever a role or avatar changes.

## Email and Cloudinary

The default `EMAIL_BACKEND=console` writes verification and reset links to API logs:

```bash
docker compose logs api
```

For real delivery, set `EMAIL_BACKEND=smtp` and configure `SMTP_HOST`, `SMTP_PORT`, `SMTP_USERNAME`, `SMTP_PASSWORD`, and `SMTP_FROM_EMAIL`.

Avatar uploads require `CLOUDINARY_CLOUD_NAME`, `CLOUDINARY_API_KEY`, and
`CLOUDINARY_API_SECRET`. Secrets remain server-side. JPEG, PNG, WebP, and GIF files up to 5 MiB are accepted and transformed to a square avatar.

## Main endpoints

| Method | Endpoint | Access | Purpose |
| --- | --- | --- | --- |
| `POST` | `/api/auth/register` | Public | Create an account |
| `GET` | `/api/auth/verify-email/{token}` | Public | Verify email |
| `POST` | `/api/auth/login` | Public | Issue access/refresh pair |
| `POST` | `/api/auth/refresh` | Public token | Rotate refresh token |
| `POST` | `/api/auth/logout` | Public token | Revoke refresh token |
| `POST` | `/api/auth/password-reset/request` | Public | Request recovery |
| `POST` | `/api/auth/password-reset/confirm` | Public token | Replace password |
| `GET` | `/api/users/me` | Bearer | Read profile; rate limited |
| `PATCH` | `/api/users/me/avatar` | Admin | Replace own avatar |
| `PATCH` | `/api/users/{id}/role` | Admin | Change a role |
| `POST` | `/api/contacts` | Bearer | Create owned contact |
| `GET` | `/api/contacts` | Bearer | List/search owned contacts |
| `GET` | `/api/contacts/upcoming-birthdays` | Bearer | Upcoming birthdays |
| `GET/PUT/PATCH/DELETE` | `/api/contacts/{id}` | Bearer | Owned-contact CRUD |

## Tests and coverage

The test layout mirrors the application responsibilities:

```text
tests/
├── unit/          # security, validation, cache, limiter, external adapters
└── integration/   # HTTP authentication, users, roles, contacts, CORS
```

Run the complete quality gate:

```bash
pytest
ruff check .
```

`pytest-cov` is configured in `pyproject.toml`. The suite fails automatically below 75% total application coverage.

## Sphinx documentation

Build warning-free HTML documentation from the application docstrings:

```bash
sphinx-build -W -b html docs docs/_build/html
```

Open `docs/_build/html/index.html` after the build. The generated directory is
excluded from version control.

## Database migrations

Migration history is retained across the three project stages:

```text
0001_create_contacts.py
0002_add_users_and_contact_ownership.py
0003_add_roles_tokens_and_password_reset.py
```

Run migrations with `alembic upgrade head`. 

## Project structure

```text
.
├── app/
│   ├── core/          # settings, Argon2, JWTs, dependencies
│   ├── db/            # async engine and sessions
│   ├── models/        # users, roles, contacts
│   ├── repositories/  # async persistence and ownership queries
│   ├── routers/       # auth, users, contacts
│   ├── schemas/       # Pydantic requests and responses
│   ├── services/      # Redis, SMTP, Cloudinary, limiter
│   ├── cli.py         # trusted administrator bootstrap
│   └── main.py
├── docs/              # Sphinx sources
├── migrations/        # Alembic revisions
├── tests/unit/
├── tests/integration/
├── docker-compose.yml
├── Dockerfile
└── render.yaml
```

## License

This educational project is available under the MIT License.
