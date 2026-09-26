Security model
==============

Passwords
---------

Passwords are hashed with Argon2 through ``pwdlib``. CPU-intensive hash and verify
operations run in worker threads so they do not block the asynchronous event loop.
Plaintext passwords are never stored or returned.

JWT tokens
----------

Access and refresh tokens are signed JWTs with issuer, audience, purpose, issue
time, expiration, unique identifier, subject, and authentication-version claims.
Refresh tokens are rotated atomically after every use. Only a SHA-256 digest of
the currently valid refresh token is stored, making replayed tokens fail.

Password recovery
-----------------

Password-reset requests return the same response for existing and missing accounts.
Verified users receive a high-entropy, short-lived, one-time opaque token. The
database stores only its digest. A successful reset clears the token, revokes the
refresh token, increments the authentication version, and invalidates Redis state.

Roles
-----

Accounts have either the ``user`` or ``admin`` role. Contact operations remain
available to authenticated users, while avatar replacement and role management
require an administrator. The first administrator is promoted through a trusted
container command rather than a public registration field.

Secrets
-------

Database credentials, JWT keys, SMTP credentials, and Cloudinary credentials are
loaded from environment variables. The real ``.env`` file is ignored by Git;
``.env.example`` documents every required setting without containing real secrets.
