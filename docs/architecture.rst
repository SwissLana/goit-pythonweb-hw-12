Architecture
============

The application uses explicit layers so HTTP concerns, validation, persistence,
and external services can be tested independently.

* ``routers`` expose FastAPI operations and translate failures into HTTP responses.
* ``schemas`` validate request and response documents with Pydantic.
* ``repositories`` contain owner-scoped SQLAlchemy queries and transactions.
* ``services`` integrate Redis, SMTP, Cloudinary, and rate limiting.
* ``core`` contains validated settings and authentication primitives.
* ``models`` define PostgreSQL entities and authorization state.

Docker Compose starts PostgreSQL, Redis, and the API. The API waits for healthy
dependencies, applies Alembic migrations, and then starts Uvicorn. Redis cache
failures degrade to PostgreSQL lookups instead of making authentication unavailable.

Contact authorization
---------------------

Every contact query includes the authenticated owner's identifier. Requests for
another user's contact return ``404 Not Found`` so the API does not disclose that
the resource exists.

Authentication cache
--------------------

Access tokens identify a user and an authentication-version number. The current
user dependency first checks ``auth:user:<id>`` in Redis. On a miss it loads the
user from PostgreSQL and caches only public profile and authorization fields with
a short TTL. Password resets increment the authentication version and invalidate
the cache, immediately rejecting previously issued access tokens.
