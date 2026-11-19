# Backend feature setup

## Requirements

The backend needs MongoDB configured with `MONGO_URI`. MongoDB must run as a
replica set (or a compatible managed cluster) because transfers, scheduled
transfer execution, dispute submission, and dispute resolution use multi-document
transactions. Account documents are versioned so independent API and worker
processes cannot silently overwrite a newer account record.

Configure a strong Flask signing key with `FLASK_SECRET_KEY`. An initial admin
account can be configured with `BANK_STAFF_USERS`, a JSON array containing a
username, Werkzeug password hash, and role for each person. Supported roles
are `admin`, `support`, `reviewer`, and `read_only`. Admins can manage staff
accounts and support flags, and review disputes; support staff can manage
flags; reviewers can review disputes; and read-only staff can search and view
operations data.

Admins can create additional staff accounts in **Staff operations → Staff
access** and assign one of the supported roles. These accounts are stored in
MongoDB with Werkzeug password hashes; plaintext passwords are never stored or
returned by the API. New passwords must be 12–128 characters. Environment-
configured accounts remain assigned roles through server configuration, while admins can
reset their passwords or revoke and reactivate access from the staff directory.
Those lifecycle changes are stored as MongoDB overrides; removing an account
from server configuration disables its override. Passwords are never viewable,
and password resets or access changes end the account's existing sessions.
The last active admin and the currently signed-in admin cannot be revoked.
Lifecycle actions are recorded in the staff audit log. Keep at least one active
admin so staff access can be recovered if another admin account is unavailable.

Generate each password hash without putting a plaintext password in shell
history:

```powershell
.\venv\Scripts\python.exe -c "from getpass import getpass; from werkzeug.security import generate_password_hash; print(generate_password_hash(getpass()))"
```

Use the returned hashes in the server's `BANK_STAFF_USERS` configuration, for
example:

```text
BANK_STAFF_USERS=[{"username":"support.alex","password_hash":"<hash>","role":"support"},{"username":"review.jamie","password_hash":"<hash>","role":"reviewer"}]
```

For backwards compatibility, setting `BANK_STAFF_USERNAME` and
`BANK_STAFF_PASSWORD_HASH` still configures one admin staff account. Prefer
`BANK_STAFF_USERS` so staff actions are attributable to individual people.
Do not commit credentials or password hashes. Do not configure default or
shared staff passwords.

Staff account flags are internal support/review markers only. They do not block
sign-in, transfers, or other customer activity. Creating and resolving a flag
requires a reason and is recorded in the staff audit log.

Account mutations require an authenticated customer session and are scoped to
that account; staff mutations require the relevant staff permission. PIN-protected
payments, transfers, scheduled-transfer creation, and PIN changes share the
account's failed-attempt lockout. Transaction-sized amounts are positive,
decimal values capped at 500 crore, except card payments and daily limits, which
are capped at $10,000. Savings-goal allocations cannot exceed the remaining
target, and staff must record resolution notes before closing a dispute.

Install dependencies and run the API:

```powershell
.\venv\Scripts\python.exe -m pip install -r requirements.txt
.\venv\Scripts\python.exe app.py
```

Open the interactive Swagger UI at `http://localhost:5000/docs`. It lists the
registered API routes and supports Try it out. Since the UI is served by the
API itself, sign in through the relevant login endpoint in Swagger UI first;
the browser will send its session cookie with subsequent requests.

When you start the API with `python app.py`, its Flask development reloader
starts and stops the scheduled-transfer worker alongside the server. If you run
the API under a production WSGI server (or without the development reloader),
run the worker as a separate process from the `backend` directory:

```powershell
.\venv\Scripts\python.exe scheduled_transfer_worker.py
```

The worker claims due records with an expiring MongoDB lease and updates the
schedule, account balances, transaction status, and history in one database
transaction. It is safe to run multiple worker instances when MongoDB
transactions are available. `SCHEDULED_TRANSFER_POLL_SECONDS` controls the
poll interval (1–3600 seconds; default 15).

Savings goals reserve a portion of the account's existing balance from
withdrawals, card purchases, and transfers. They track an allocation inside this
demo account; they do not move funds to a separate bank product or external
account. This project is not a production banking or payment system.
