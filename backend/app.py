import os
import re
import subprocess
import sys
import time
import hmac
import copy
import json
import pyotp
import io
import base64
import qrcode
import logging
import calendar
from datetime import datetime, timezone, timedelta
import secrets
from decimal import Decimal, InvalidOperation
from flask import Flask, jsonify, request, session
from flask_cors import CORS
from flask_swagger_ui import get_swaggerui_blueprint
from werkzeug.security import check_password_hash, generate_password_hash
from pymongo import ReturnDocument
from pymongo.errors import DuplicateKeyError, PyMongoError

import bank_service as bank
from openapi_spec import build_openapi_spec


app = Flask(__name__)
swaggerui_blueprint = get_swaggerui_blueprint(
    "/docs",
    "/openapi.json",
    config={"app_name": "BlueBank API"},
)
app.register_blueprint(swaggerui_blueprint, url_prefix="/docs")

app.config.update(
    SECRET_KEY=os.environ.get(
        "FLASK_SECRET_KEY",
        "change-this-development-secret"
    ),
    SESSION_COOKIE_HTTPONLY=True,
    SESSION_COOKIE_SAMESITE="Lax",
    SESSION_COOKIE_SECURE=False,
    PERMANENT_SESSION_LIFETIME=8 * 60 * 60,
)

CORS(
    app,
    supports_credentials=True,
    origins=["http://localhost:5173"],
)

bank.load_data()

# Session security
INACTIVITY_TIMEOUT = 15 * 60       # 15 minutes
ABSOLUTE_SESSION_TIMEOUT = 8 * 60 * 60  # 8 hours
MAX_TRANSACTION_AMOUNT = Decimal("5000000000.00")
SPENDING_CATEGORIES = (
    "Bills",
    "Education",
    "Entertainment",
    "Food",
    "Health",
    "Shopping",
    "Transport",
    "Travel",
    "Other",
)
logger = logging.getLogger(__name__)


class StaffAccessUnavailable(Exception):
    pass


STAFF_ROLES = {
    "admin": {"read", "flags:manage", "disputes:review", "audit:read", "staff:manage"},
    "support": {"read", "flags:manage", "audit:read"},
    "reviewer": {"read", "disputes:review", "audit:read"},
    "read_only": {"read", "audit:read"},
}
staff_account_flags = bank.mongo_db["staff_account_flags"]
staff_users_collection = bank.mongo_db["staff_users"]
staff_users_collection.create_index("username_key", unique=True)
staff_access_guard_collection = bank.mongo_db["staff_access_guard"]
staff_account_flags.create_index(
    [("account_number", 1), ("status", 1), ("created_at", -1)]
)
staff_account_flags.create_index(
    [("account_number", 1)],
    unique=True,
    partialFilterExpression={"status": "ACTIVE"},
)

def error(message, status=400):
    return jsonify({
        "success": False,
        "message": message
    }), status


@app.errorhandler(StaffAccessUnavailable)
def handle_staff_access_unavailable(_exception):
    return error("Staff access is temporarily unavailable.", 503)


def request_json():
    data = request.get_json(silent=True)
    return data if isinstance(data, dict) else None


def authenticated_account():
    account_number = session.get("account_number")

    if not account_number:
        return None

    if session.get("server_session_id"):
        return bank.refresh_account(account_number)

    return bank.accounts.get(account_number)


def register_server_session(role, account_number=None, staff_username=None):
    session_id = secrets.token_urlsafe(32)
    now = datetime.now(timezone.utc).isoformat()
    session_record = {
        "_id": session_id,
        "role": role,
        "account_number": account_number,
        "created_at": now,
        "last_seen_at": now,
        "revoked_at": None,
        "device": request.user_agent.platform or "Unknown device",
        "browser": request.user_agent.browser or "Unknown browser",
    }
    if staff_username:
        session_record["staff_username_key"] = staff_username.strip().casefold()
    bank.sessions_collection.insert_one(session_record)
    return session_id


def active_session_record():
    session_id = session.get("server_session_id")
    if not session_id:
        return None

    return bank.sessions_collection.find_one({
        "_id": session_id,
        "revoked_at": None,
    })


def require_staff(permission="read"):
    if session.get("session_role") != "staff":
        return False
    active_record = active_session_record()
    if active_record is None:
        return False
    staff_username = session.get("staff_username")
    if isinstance(staff_username, str):
        try:
            stored_user = staff_users_collection.find_one(
                {"username_key": staff_username.strip().casefold()},
                {
                    "_id": 0,
                    "active": 1,
                    "password_changed_at": 1,
                    "access_revoked_at": 1,
                },
            )
        except PyMongoError as exc:
            logger.exception("Could not verify staff account access")
            raise StaffAccessUnavailable() from exc
        if stored_user is not None and stored_user.get("active") is False:
            return False
        session_created = _iso_datetime(active_record.get("created_at"))
        if session_created is not None and stored_user is not None:
            for field in ("password_changed_at", "access_revoked_at"):
                changed_at = _iso_datetime(stored_user.get(field))
                if changed_at is not None and session_created < changed_at:
                    return False
    if session.get("staff_role") not in STAFF_ROLES:
        return False
    return permission in STAFF_ROLES.get(session.get("staff_role"), set())


def configured_staff_users():
    users_setting = os.environ.get("BANK_STAFF_USERS", "").strip()
    if users_setting:
        try:
            users = json.loads(users_setting)
        except json.JSONDecodeError as exc:
            raise ValueError("BANK_STAFF_USERS must contain valid JSON.") from exc
        if not isinstance(users, list) or not users:
            raise ValueError("BANK_STAFF_USERS must be a non-empty JSON list.")
        normalized = {}
        for user in users:
            if not isinstance(user, dict):
                raise ValueError("Every BANK_STAFF_USERS entry must be an object.")
            username = user.get("username")
            password_hash = user.get("password_hash")
            role = user.get("role")
            username_key = (
                username.strip().casefold()
                if isinstance(username, str)
                else ""
            )
            if (
                not isinstance(username, str)
                or not username.strip()
                or not isinstance(password_hash, str)
                or not password_hash
                or not isinstance(role, str)
                or role not in STAFF_ROLES
                or username_key in normalized
            ):
                raise ValueError(
                    "Staff users need unique usernames, password_hash values, "
                    "and a supported role."
                )
            normalized[username_key] = {
                "username": username.strip(),
                "password_hash": password_hash,
                "role": role,
            }
        return normalized

    username = os.environ.get("BANK_STAFF_USERNAME", "")
    password_hash = os.environ.get("BANK_STAFF_PASSWORD_HASH", "")
    if username and password_hash:
        return {
            username.strip().casefold(): {
                "username": username.strip(),
                "password_hash": password_hash,
                "role": "admin",
            }
        }
    return {}


def staff_page_params():
    try:
        page = int(request.args.get("page", "1"))
        page_size = int(request.args.get("page_size", "25"))
    except (TypeError, ValueError):
        return None
    if page < 1 or page_size < 1 or page_size > 100:
        return None
    return page, page_size


def _mask_email(email):
    if not isinstance(email, str) or "@" not in email:
        return ""
    local_part, domain = email.rsplit("@", 1)
    if not local_part or not domain:
        return ""
    return f"{local_part[0]}***@{domain}"


def _iso_datetime(value):
    if not isinstance(value, str) or not value:
        return None
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return None
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    return parsed.astimezone(timezone.utc)


def _staff_account_ref(account_number):
    return hmac.new(
        str(app.config["SECRET_KEY"]).encode("utf-8"),
        str(account_number).encode("utf-8"),
        "sha256",
    ).hexdigest()[:32]


def _resolve_staff_account_ref(account_ref):
    for record in bank.accounts_collection.find(
        {},
        {"account_number": 1},
    ):
        account_number = str(record.get("account_number", ""))
        if hmac.compare_digest(_staff_account_ref(account_number), account_ref):
            return account_number
    return None


def _record_staff_access(action, result_count):
    try:
        bank.audit_log_collection.insert_one({
            "id": "AUD-" + secrets.token_hex(8).upper(),
            "actor": session.get("staff_username", "staff"),
            "action": action,
            "entity_id": "STAFF_SEARCH",
            "details": {"result_count": result_count},
            "created_at": datetime.now(timezone.utc).isoformat(),
        })
    except Exception:
        logger.exception("Could not record staff data access")
        return False
    return True

def session_timed_out():
    now = time.time()

    login_time = session.get("login_time")
    last_activity = session.get("last_activity")

    if not login_time or not last_activity:
        return True

    if now - login_time >= ABSOLUTE_SESSION_TIMEOUT:
        return True

    if now - last_activity >= INACTIVITY_TIMEOUT:
        return True

    return False

def create_notification(
    account,
    notification_type,
    title,
    message
):
    notification = {
        "id": "NOTIF-" + secrets.token_hex(6).upper(),
        "type": notification_type,
        "title": title,
        "message": message,
        "read": False,
        "created_at": datetime.now(timezone.utc).isoformat(),
    }

    account.setdefault("notifications", []).insert(
        0,
        notification
    )

    # Keep only the latest 50 notifications.
    account["notifications"] = account["notifications"][:50]

    return notification


def should_send_transfer_notification(account):
    preferences = account.get("alert_preferences") or bank.default_alert_preferences()
    return preferences.get("transfer_alerts_enabled", True)


def create_transaction_alerts(account, transaction, previous_balance):
    preferences = account.get("alert_preferences") or bank.default_alert_preferences()
    amount = Decimal(str(transaction.get("amount", "0")))
    if preferences.get("transaction_alerts_enabled", True):
        threshold = preferences.get("large_transaction_threshold")
        if threshold is not None and amount >= Decimal(str(threshold)):
            transaction_type = transaction.get("type", "transaction")
            create_notification(
                account,
                "WARNING",
                "Large transaction",
                f"A {transaction_type.lower().replace('_', ' ')} for ${amount:.2f} was recorded.",
            )

    low_balance = preferences.get("low_balance_threshold")
    if (
        low_balance is not None
        and previous_balance
        - (account["balance"] - bank.available_balance(account))
        > Decimal(str(low_balance))
        and bank.available_balance(account) <= Decimal(str(low_balance))
    ):
        create_notification(
            account,
            "WARNING",
            "Low balance",
            f"Your available account balance is ${account['balance']:.2f}.",
        )


def create_security_event(account, event, status="SUCCESS"):
    security_event = {
        "id": "SEC-" + secrets.token_hex(6).upper(),
        "event": event,
        "status": status,
        "created_at": datetime.now(timezone.utc).isoformat(),
        "device": request.user_agent.platform or "Unknown device",
        "browser": request.user_agent.browser or "Unknown browser",
    }

    account.setdefault("security_activity", []).insert(
        0,
        security_event
    )

    account["security_activity"] = account["security_activity"][:50]

    return security_event


def pin_lock_response(account):
    now = time.time()
    locked_until = account.get("locked_until", 0)
    if not isinstance(locked_until, (int, float)) or isinstance(locked_until, bool):
        return error("Account security state is unavailable.", 503)
    if locked_until > now:
        remaining = max(1, int(locked_until - now + 0.999))
        return error(
            f"Account temporarily locked. Try again in {remaining} seconds.",
            423,
        )
    return None


def account_pin_matches(account, pin):
    return (
        isinstance(pin, str)
        and re.fullmatch(r"[0-9]{4}", pin) is not None
        and bank.verify_pin(
            pin,
            account.get("pin_salt"),
            account.get("pin_hash"),
        )
    )


def record_failed_pin_attempt(account, notification=None):
    lock_response = pin_lock_response(account)
    if lock_response is not None:
        return lock_response

    previous_attempts = account.get("failed_attempts", 0)
    previous_locked_until = account.get("locked_until", 0)
    if type(previous_attempts) is not int or previous_attempts < 0:
        return error("Account security state is unavailable.", 503)

    attempts = previous_attempts if previous_locked_until == 0 else 0
    attempts += 1
    locked = attempts >= bank.MAX_PIN_ATTEMPTS
    account["failed_attempts"] = 0 if locked else attempts
    account["locked_until"] = time.time() + bank.LOCK_DURATION if locked else 0

    had_notifications = "notifications" in account
    previous_notifications = copy.deepcopy(account.get("notifications", []))
    if notification is not None:
        create_notification(account, *notification)

    if not bank.save_data():
        account["failed_attempts"] = previous_attempts
        account["locked_until"] = previous_locked_until
        if had_notifications:
            account["notifications"] = previous_notifications
        else:
            account.pop("notifications", None)
        return error("The PIN attempt could not be recorded. Please try again.", 503)

    if locked:
        return error(
            "Maximum incorrect attempts reached. Account locked for 60 seconds.",
            423,
        )
    remaining = bank.MAX_PIN_ATTEMPTS - attempts
    return error(
        f"Incorrect security PIN. {remaining} attempt(s) remaining.",
        401,
    )


def clear_pin_failures(account):
    account["failed_attempts"] = 0
    account["locked_until"] = 0


@app.before_request
def enforce_session_timeout():
    if request.path in (
        "/api/login",
        "/api/staff/login",
        "/api/register",
        "/api/health",
        "/openapi.json",
    ):
        return None
    if request.path == "/docs" or request.path.startswith("/docs/"):
        return None

    if not session.get("account_number") and not session.get("session_role"):
        return None

    if session_timed_out():
        session.clear()

        return jsonify({
            "success": False,
            "message": "Your session has expired. Please login again.",
            "session_expired": True,
        }), 401

    session_id = session.get("server_session_id")
    if session_id:
        try:
            record = active_session_record()
            if (
                record is None
                or record.get("role") != session.get("session_role")
                or record.get("account_number") != session.get("account_number")
            ):
                session.clear()
                return jsonify({
                    "success": False,
                    "message": "This session is no longer active. Please sign in again.",
                    "session_expired": True,
                }), 401
            bank.sessions_collection.update_one(
                {"_id": session_id, "revoked_at": None},
                {"$set": {"last_seen_at": datetime.now(timezone.utc).isoformat()}},
            )
        except Exception:
            logger.exception("Could not verify the active server session")
            return error("Session storage is unavailable. Please try again.", 503)

    session["last_activity"] = time.time()

    return None


@app.get("/api/health")
def health():
    return jsonify({
        "success": True,
        "message": "Bank API is running"
    })


@app.get("/openapi.json")
def openapi_document():
    return jsonify(build_openapi_spec(app))


@app.post("/api/register")
def register():
    data = request_json()

    if data is None:
        return error("A JSON request body is required.")

    name = data.get("name")
    age = data.get("age")
    pin = data.get("pin")

    if not isinstance(name, str) or not bank.is_valid_name(name.strip()):
        return error(
            "Enter a valid name using letters, spaces, hyphens or apostrophes."
        )

    if (
        isinstance(age, bool)
        or not str(age).isdigit()
        or not 18 <= int(age) <= 120
    ):
        return error(
            "Age must be a whole number between 18 and 120."
        )

    if not isinstance(pin, str) or not bank.is_strong_pin(pin):
        return error(
            "Choose a valid, strong 4-digit PIN."
        )

    if not bank.storage_ready:
        return error(
            "Account storage is unavailable.",
            503
        )

    account_number = bank.generate_account_number()
    salt, pin_hash = bank.hash_pin(pin)

    bank.accounts[account_number] = {
        "name": " ".join(name.split()),
        "age": int(age),
        "email": "",
        "account_number": account_number,
        "balance": __import__("decimal").Decimal("0.00"),
        "pin_salt": salt,
        "pin_hash": pin_hash,
        "failed_attempts": 0,
        "locked_until": 0,
        "transactions": [],
        "beneficiaries": [],
        "notifications": [],
        "security_activity": [],
    }

    if not bank.save_data():
        del bank.accounts[account_number]

        return error(
            "Account creation failed because data could not be saved.",
            500
        )

    return jsonify({
        "success": True,
        "message": (
            "Account created successfully. "
            "Please save your account number."
        ),
        "account_number": account_number,
        "name": bank.accounts[account_number]["name"],
    }), 201

@app.post("/api/login/verify-2fa")
def verify_login_2fa():
    data = request_json()

    if data is None:
        return error("A JSON request body is required.")

    account_number = session.get("pending_2fa_account")

    if not account_number:
        return error("No pending two-factor authentication request.", 400)

    code = str(data.get("code", "")).strip()

    if not re.fullmatch(r"[0-9]{6}", code):
        return error("Authenticator code must contain exactly 6 digits.")

    account = bank.accounts.get(account_number)

    if account is None:
        session.clear()
        return error("Invalid authentication request.", 401)

    two_factor = account.get("two_factor", {})
    secret = two_factor.get("secret")

    if not two_factor.get("enabled") or not secret:
        session.clear()
        return error("Two-factor authentication is not enabled.", 400)

    totp = pyotp.TOTP(secret)

    if not totp.verify(code, valid_window=1):
        return error("Invalid authenticator code.", 401)

    create_security_event(
        account,
        "Two-factor authentication login",
        "SUCCESS"
    )

    if account.get("alert_preferences", {}).get("sign_in_alerts_enabled", True):
        create_notification(
            account,
            "INFO",
            "New sign-in",
            "Your account was accessed with two-factor authentication.",
        )

    if not bank.save_data():
        return error("Unable to save login activity. Please try again.", 503)

    try:
        server_session_id = register_server_session(
            "customer",
            account_number,
        )
    except Exception:
        logger.exception("Could not register customer session")
        return error("Could not start a secure session. Please try again.", 503)

    session.clear()
    session["account_number"] = account_number
    session["session_role"] = "customer"
    session["server_session_id"] = server_session_id
    session.permanent = True
    session["login_time"] = time.time()
    session["last_activity"] = time.time()

    return jsonify({
        "success": True,
        "message": "Login successful.",
        "account": bank.public_account(account)
    })

@app.get("/api/2fa/status")
def two_fa_status():
    account = authenticated_account()

    if account is None:
        return error("Authentication required.", 401)

    two_factor = account.get("two_factor", {})

    return jsonify({
        "enabled": bool(two_factor.get("enabled", False))
    })


@app.post("/api/2fa/setup")
def two_fa_setup():
    account = authenticated_account()

    if account is None:
        return error("Authentication required.", 401)

    two_factor = account.setdefault(
        "two_factor",
        {
            "enabled": False,
            "secret": None,
        }
    )

    if two_factor.get("enabled"):
        return error("Two-factor authentication is already enabled.", 409)

    secret = pyotp.random_base32()

    account["two_factor"] = {
        "enabled": False,
        "secret": secret,
    }

    account_number = account["account_number"]

    totp = pyotp.TOTP(secret)

    provisioning_uri = totp.provisioning_uri(
        name=account_number,
        issuer_name="BlueBank",
    )

    qr = qrcode.QRCode(
        version=1,
        box_size=10,
        border=4,
    )

    qr.add_data(provisioning_uri)
    qr.make(fit=True)

    qr_image = qr.make_image()

    buffer = io.BytesIO()
    qr_image.save(buffer, format="PNG")

    qr_data = base64.b64encode(
        buffer.getvalue()
    ).decode("utf-8")

    return jsonify({
        "success": True,
        "secret": secret,
        "qr_code": f"data:image/png;base64,{qr_data}",
        "provisioning_uri": provisioning_uri,
    })


@app.post("/api/2fa/verify-setup")
def two_fa_verify_setup():
    account = authenticated_account()

    if account is None:
        return error("Authentication required.", 401)

    data = request_json()

    if data is None:
        return error("A JSON request body is required.")

    code = str(data.get("code", "")).strip()

    if not re.fullmatch(r"[0-9]{6}", code):
        return error("Enter a valid 6-digit authenticator code.")

    two_factor = account.get("two_factor", {})
    secret = two_factor.get("secret")

    if not secret:
        return error("Two-factor setup has not been started.", 400)

    totp = pyotp.TOTP(secret)

    if not totp.verify(code, valid_window=1):
        return error("Invalid authenticator code.", 401)

    two_factor["enabled"] = True

    if not bank.save_data():
        return error(
            "Unable to save two-factor authentication status.",
            503
        )

    create_security_event(
        account,
        "Two-factor authentication enabled",
        "SUCCESS"
    )

    bank.save_data()

    return jsonify({
        "success": True,
        "message": "Two-factor authentication enabled successfully."
    })


@app.post("/api/2fa/disable")
def two_fa_disable():
    account = authenticated_account()

    if account is None:
        return error("Authentication required.", 401)

    data = request_json()

    if data is None:
        return error("A JSON request body is required.")

    code = str(data.get("code", "")).strip()

    two_factor = account.get("two_factor", {})
    secret = two_factor.get("secret")

    if not two_factor.get("enabled") or not secret:
        return error("Two-factor authentication is not enabled.", 400)

    if not re.fullmatch(r"[0-9]{6}", code):
        return error("Enter a valid 6-digit authenticator code.")

    totp = pyotp.TOTP(secret)

    if not totp.verify(code, valid_window=1):
        return error("Invalid authenticator code.", 401)

    account["two_factor"] = {
        "enabled": False,
        "secret": None,
    }

    create_security_event(
        account,
        "Two-factor authentication disabled",
        "SUCCESS"
    )

    if not bank.save_data():
        return error(
            "Unable to save two-factor authentication status.",
            503
        )

    return jsonify({
        "success": True,
        "message": "Two-factor authentication disabled successfully."
    })

@app.post("/api/forgot-pin")
def forgot_pin():
    data = request_json()

    if data is None:
        return error("A JSON request body is required.")

    account_number = str(
        data.get("account_number", "")
    ).strip()

    if not re.fullmatch(r"[0-9]{11}", account_number):
        return error(
            "Account number must contain exactly 11 digits."
        )

    account = bank.accounts.get(account_number)

    if account is None:
        return error("Unable to start PIN recovery.", 404)

    two_factor = account.get("two_factor", {})

    if not two_factor.get("enabled") or not two_factor.get("secret"):
        return error(
            "PIN recovery requires Google Authenticator to be enabled.",
            400
        )

    return jsonify({
        "success": True,
        "message": "Account verified. Enter your Google Authenticator code."
    })


@app.post("/api/forgot-pin/verify-2fa")
def forgot_pin_verify_2fa():
    data = request_json()

    if data is None:
        return error("A JSON request body is required.")

    account_number = str(
        data.get("account_number", "")
    ).strip()

    code = str(
        data.get("code", "")
    ).strip()

    if not re.fullmatch(r"[0-9]{11}", account_number):
        return error(
            "Account number must contain exactly 11 digits."
        )

    if not re.fullmatch(r"[0-9]{6}", code):
        return error(
            "Authenticator code must contain exactly 6 digits."
        )

    account = bank.accounts.get(account_number)

    if account is None:
        return error("Unable to verify PIN recovery.", 401)

    two_factor = account.get("two_factor", {})
    secret = two_factor.get("secret")

    if not two_factor.get("enabled") or not secret:
        return error(
            "Two-factor authentication is not enabled.",
            400
        )

    totp = pyotp.TOTP(secret)

    if not totp.verify(code, valid_window=1):
        return error(
            "Invalid authenticator code.",
            401
        )

    session.clear()

    session["pending_pin_reset_account"] = account_number
    session["pin_reset_verified_at"] = time.time()

    return jsonify({
        "success": True,
        "message": "Authenticator verified. You can now set a new PIN."
    })


@app.post("/api/reset-pin")
def reset_pin():
    data = request_json()

    if data is None:
        return error("A JSON request body is required.")

    account_number = session.get(
        "pending_pin_reset_account"
    )

    verified_at = session.get(
        "pin_reset_verified_at"
    )

    if not account_number or not verified_at:
        return error(
            "PIN reset verification is required.",
            401
        )

    # Allow only 5 minutes between 2FA verification
    # and PIN reset.
    if time.time() - verified_at > 300:
        session.clear()

        return error(
            "PIN reset session expired. Please start again.",
            401
        )

    requested_account_number = str(
        data.get("account_number", "")
    ).strip()

    new_pin = data.get("new_pin")

    if requested_account_number != account_number:
        return error(
            "Invalid PIN reset request.",
            401
        )

    if (
        not isinstance(new_pin, str)
        or not re.fullmatch(r"[0-9]{4}", new_pin)
    ):
        return error(
            "PIN must contain exactly 4 digits."
        )

    if not bank.is_strong_pin(new_pin):
        return error(
            "PIN does not meet the security requirements."
        )

    account = bank.accounts.get(account_number)

    if account is None:
        session.clear()

        return error(
            "Invalid PIN reset request.",
            401
        )

    salt, pin_hash = bank.hash_pin(new_pin)

    account["pin_salt"] = salt
    account["pin_hash"] = pin_hash

    account["failed_attempts"] = 0
    account["locked_until"] = 0

    create_security_event(
        account,
        "PIN reset",
        "SUCCESS"
    )

    if not bank.save_data():
        return error(
            "Unable to save the new PIN. Please try again.",
            503
        )

    session.clear()

    return jsonify({
        "success": True,
        "message": "PIN reset successfully."
    })

@app.post("/api/login")
def login():
    data = request_json()

    if data is None:
        return error("A JSON request body is required.")

    account_number = str(
        data.get("account_number", "")
    ).strip()

    pin = data.get("pin")

    if not re.fullmatch(r"[0-9]{11}", account_number):
        return error(
            "Account number must contain exactly 11 digits."
        )

    account = bank.refresh_account(account_number)

    if account is None:
        return error(
            "Invalid account number or PIN.",
            401
        )

    if "pin_hash" not in account:
        return error(
            "This legacy account needs PIN setup through "
            "the account migration process.",
            409
        )

    now = time.time()

    if now < account.get("locked_until", 0):
        remaining = max(
            1,
            int(account["locked_until"] - now + 0.999)
        )

        return error(
            f"Account temporarily locked. "
            f"Try again in {remaining} seconds.",
            423
        )

    if account.get("locked_until", 0) > 0:
        account["failed_attempts"] = 0
        account["locked_until"] = 0

    if (
        not isinstance(pin, str)
        or not re.fullmatch(r"[0-9]{4}", pin)
        or not bank.verify_pin(
            pin,
            account["pin_salt"],
            account["pin_hash"]
        )
    ):
        account["failed_attempts"] = (
            account.get("failed_attempts", 0) + 1
        )

        if account["failed_attempts"] >= bank.MAX_PIN_ATTEMPTS:
            account["locked_until"] = (
                time.time() + bank.LOCK_DURATION
            )

        if not bank.save_data():
            return error(
                "Login denied because security status could not be saved.",
                503
            )

        if account["failed_attempts"] >= bank.MAX_PIN_ATTEMPTS:
            return error(
                "Maximum incorrect attempts reached. "
                "Account locked for 60 seconds.",
                423
            )

        return error(
            f"Incorrect PIN. "
            f"{bank.MAX_PIN_ATTEMPTS - account['failed_attempts']} "
            f"attempt(s) remaining.",
            401
        )

    account["failed_attempts"] = 0
    account["locked_until"] = 0

    if not bank.save_data():
        return error(
            "Unable to save login security status. Please try again.",
            503
        )

    two_factor = account.get("two_factor", {})

    if two_factor.get("enabled") and two_factor.get("secret"):
        session.clear()

        session["pending_2fa_account"] = account_number
        session["login_time"] = time.time()

        return jsonify({
            "success": True,
            "requires_2fa": True,
            "message": "Enter your Google Authenticator code."
        })

    create_security_event(
        account,
        "Login",
        "SUCCESS"
    )

    if account.get("alert_preferences", {}).get("sign_in_alerts_enabled", True):
        create_notification(
            account,
            "INFO",
            "New sign-in",
            "Your account was signed in from a new session.",
        )

    if not bank.save_data():
        return error("Unable to save login activity. Please try again.", 503)

    try:
        server_session_id = register_server_session(
            "customer",
            account_number,
        )
    except Exception:
        logger.exception("Could not register customer session")
        return error("Could not start a secure session. Please try again.", 503)

    session.clear()
    session["account_number"] = account_number
    session["session_role"] = "customer"
    session["server_session_id"] = server_session_id
    session.permanent = True
    session["login_time"] = time.time()
    session["last_activity"] = time.time()

    return jsonify({
        "success": True,
        "message": "Login successful.",
        "account": bank.public_account(account)
    })


@app.post("/api/staff/login")
def staff_login():
    data = request_json()
    if data is None:
        return error("A JSON request body is required.")

    if app.config["SECRET_KEY"] == "change-this-development-secret":
        return error("Staff access requires a configured FLASK_SECRET_KEY.", 503)

    username = data.get("username")
    password = data.get("password")

    try:
        staff_users = configured_staff_users()
    except ValueError:
        logger.exception("Staff user configuration is invalid")
        return error("Staff access configuration is invalid.", 503)

    username_key = username.strip().casefold() if isinstance(username, str) else ""
    if not username_key:
        return error("Invalid staff credentials.", 401)
    try:
        stored_user = staff_users_collection.find_one(
            {"username_key": username_key},
            {"_id": 0, "username_key": 0},
        )
    except Exception:
        logger.exception("Could not load a staff account")
        return error("Staff access is temporarily unavailable.", 503)

    staff_user = staff_users.get(username_key)
    if staff_user is not None:
        if (
            stored_user is not None
            and stored_user.get("source") == "environment"
        ):
            if stored_user.get("active") is False:
                return error("Invalid staff credentials.", 401)
            staff_user = dict(staff_user)
            staff_user["password_hash"] = stored_user.get(
                "password_hash",
                staff_user["password_hash"],
            )
    elif (
        stored_user is not None
        and stored_user.get("source") != "environment"
        and stored_user.get("active", True) is True
    ):
        staff_user = stored_user
    if not staff_users and staff_user is None:
        return error("Staff access is not configured on this server.", 503)
    valid_password = isinstance(password, str) and staff_user is not None
    if valid_password:
        try:
            valid_password = check_password_hash(
                staff_user["password_hash"],
                password,
            )
        except ValueError:
            logger.exception("A staff password hash is invalid")
            return error("Staff access configuration is invalid.", 503)
    if not valid_password:
        return error("Invalid staff credentials.", 401)

    try:
        server_session_id = register_server_session(
            "staff",
            staff_username=staff_user.get("username", username.strip()),
        )
    except Exception:
        logger.exception("Could not register staff session")
        return error("Could not start a secure staff session.", 503)

    session.clear()
    session["session_role"] = "staff"
    session["staff_username"] = staff_user.get("username", username.strip())
    session["staff_role"] = staff_user["role"]
    session["server_session_id"] = server_session_id
    session.permanent = True
    session["login_time"] = time.time()
    session["last_activity"] = time.time()

    return jsonify({
        "success": True,
        "message": "Staff sign-in successful.",
        "staff": {
            "username": staff_user.get("username", username.strip()),
            "role": staff_user["role"],
        },
    })


@app.post("/api/logout")
def logout():
    session_id = session.get("server_session_id")
    if session_id:
        try:
            bank.sessions_collection.update_one(
                {"_id": session_id, "revoked_at": None},
                {"$set": {"revoked_at": datetime.now(timezone.utc).isoformat()}},
            )
        except Exception:
            logger.exception("Could not revoke session during logout")
            return error("Could not securely end this session.", 503)

    session.clear()

    return jsonify({
        "success": True,
        "message": "Logged out successfully."
    })


@app.get("/api/account")
def account_details():
    account = authenticated_account()

    if account is None:
        return error("Please login first.", 401)

    return jsonify({
        "success": True,
        "account": bank.public_account(account)
    })

@app.get("/api/cards")
def get_cards():
    account = authenticated_account()

    if account is None:
        return error("Please login first.", 401)

    changed = False

    for card in account.get("cards", []):
        if bank.refresh_card_status(card):
            changed = True

    if changed:
        bank.save_data()

    cards = [
        bank.public_card(card)
        for card in account.get("cards", [])
    ]

    virtual_cards = [
        bank.public_virtual_card(card)
        for card in account.get(
            "virtual_cards",
            [],
        )
    ]

    return jsonify({
        "success": True,
        "cards": cards,
        "virtual_cards": virtual_cards,
    })

@app.get("/api/cards/<card_id>/transactions")
def card_transactions(card_id):
    account = authenticated_account()

    if account is None:
        return error("Please login first.", 401)

    card = next(
        (
            item
            for item in account.get("cards", [])
            if item.get("id") == card_id
        ),
        None,
    )

    if card is None:
        return error("Card not found.", 404)

    transactions = [
        bank.public_card_transaction(item)
        for item in card.get(
            "transactions",
            []
        )
    ]

    return jsonify({
        "success": True,
        "transactions": transactions,
    })

@app.get("/api/cards/<card_id>/analytics")
def card_analytics(card_id):
    account = authenticated_account()

    if account is None:
        return error("Please login first.", 401)

    card = next(
        (
            item
            for item in account.get("cards", [])
            if item.get("id") == card_id
        ),
        None,
    )

    if card is None:
        return error("Card not found.", 404)

    categories = {}
    total = Decimal("0.00")

    for transaction in card.get(
        "transactions",
        [],
    ):
        if transaction.get("type") != "CARD_PAYMENT":
            continue

        amount = Decimal(
            str(transaction.get("amount", "0"))
        )

        category = transaction.get(
            "category",
            "Other",
        )

        categories[category] = (
            categories.get(
                category,
                Decimal("0.00")
            )
            + amount
        )

        total += amount

    result = [
        {
            "category": category,
            "amount": str(amount),
        }
        for category, amount
        in sorted(
            categories.items(),
            key=lambda item: item[1],
            reverse=True,
        )
    ]

    return jsonify({
        "success": True,
        "total_spending": str(total),
        "categories": result,
    })

@app.post("/api/cards/<card_id>/payment")
def card_payment(card_id):
    account = authenticated_account()

    if account is None:
        return error("Please login first.", 401)

    card = next(
        (
            item
            for item in account.get("cards", [])
            if item.get("id") == card_id
        ),
        None,
    )

    if card is None:
        return error("Card not found.", 404)

    bank.refresh_card_status(card)

    if card.get("status") != "ACTIVE":
        return error(
            f"Card is {card.get('status', 'UNAVAILABLE').lower()} "
            "and cannot be used.",
            400,
        )

    data = request_json()

    if data is None:
        return error(
            "A JSON request body is required."
        )

    merchant = data.get("merchant")
    category = data.get(
        "category",
        "Other",
    )
    pin = data.get("pin")
    amount = bank.parse_amount(
        data.get("amount")
    )

    if (
        not isinstance(merchant, str)
        or not merchant.strip()
    ):
        return error(
            "Merchant name is required."
        )

    if len(merchant.strip()) > 100:
        return error(
            "Merchant name is too long."
        )

    if category not in SPENDING_CATEGORIES:
        return error("Choose a supported spending category.")

    if amount is None:
        return error(
            "Enter a valid payment amount."
        )

    if amount > Decimal("10000.00"):
        return error(
            "Single card payment cannot exceed $10,000.",
            400,
        )

    if not isinstance(pin, str):
        return error(
            "Security PIN is required."
        )

    lock_response = pin_lock_response(account)
    if lock_response is not None:
        return lock_response

    if not account_pin_matches(account, pin):
        return record_failed_pin_attempt(
            account,
            (
                "error",
                "Card payment failed",
                "A card payment was declined because the security PIN was incorrect.",
            ),
        )

    previous_failed_attempts = account.get("failed_attempts", 0)
    previous_locked_until = account.get("locked_until", 0)
    clear_pin_failures(account)

    daily_spent = bank.card_daily_spending(
        card
    )

    daily_limit = Decimal(
        str(card["daily_limit"])
    )

    if daily_spent + amount > daily_limit:
        return error(
            (
                "Daily card spending limit exceeded. "
                f"Remaining limit: "
                f"${daily_limit - daily_spent:.2f}"
            ),
            400,
        )

    if amount > bank.available_balance(account):
        failed = record_failed_transaction(
            account,
            "CARD_PAYMENT",
            amount,
            "Insufficient available funds",
            merchant=merchant.strip(),
            category=category,
        )
        if failed is None:
            return error("Could not save the failed payment record.", 503)
        return error("Insufficient available funds.", 400)

    now = datetime.now(timezone.utc)

    previous_balance = account["balance"]
    had_card_transactions = "transactions" in card
    had_account_transactions = "transactions" in account
    had_notifications = "notifications" in account
    previous_card_transactions = copy.deepcopy(card.get("transactions", []))
    previous_account_transactions = copy.deepcopy(account.get("transactions", []))
    previous_notifications = copy.deepcopy(account.get("notifications", []))
    balance = account["balance"]
    balance -= amount

    transaction = {
        "id": (
            "CARDTXN-"
            + secrets.token_hex(6).upper()
        ),
        "type": "CARD_PAYMENT",
        "merchant": merchant.strip(),
        "category": category,
        "amount": str(amount),
        "status": "COMPLETED",
        "created_at": now.isoformat(),
        "balance_after": str(balance),
    }

    account["balance"] = balance

    card.setdefault(
        "transactions",
        []
    ).insert(
        0,
        transaction,
    )

    card["transactions"] = (
        card["transactions"][:100]
    )

    account.setdefault(
        "transactions",
        []
    ).insert(
        0,
        transaction,
    )

    account["transactions"] = (
        account["transactions"][:200]
    )

    create_transaction_alerts(account, transaction, previous_balance)
    create_notification(
        account,
        "SUCCESS",
        "Card payment completed",
        (
            f"${amount:.2f} paid to "
            f"{merchant.strip()} using your card ending in "
            f"{card['last_four']}."
        ),
    )

    if not bank.save_data():
        account["balance"] = previous_balance
        if had_card_transactions:
            card["transactions"] = previous_card_transactions
        else:
            card.pop("transactions", None)
        if had_account_transactions:
            account["transactions"] = previous_account_transactions
        else:
            account.pop("transactions", None)
        if had_notifications:
            account["notifications"] = previous_notifications
        else:
            account.pop("notifications", None)
        account["failed_attempts"] = previous_failed_attempts
        account["locked_until"] = previous_locked_until

        return error(
            "Payment failed. No changes were saved.",
            500,
        )

    return jsonify({
        "success": True,
        "message": "Card payment completed successfully.",
        "transaction": bank.public_card_transaction(
            transaction
        ),
        "balance": str(account["balance"]),
        "daily_spent": str(
            bank.card_daily_spending(card)
        ),
        "daily_limit": card["daily_limit"],
    })

@app.post("/api/cards")
def create_card():
    account = authenticated_account()

    if account is None:
        return error("Please login first.", 401)

    for card in account.get("cards", []):
        bank.refresh_card_status(card)

        if card.get("status") in {
            "ISSUED",
            "ACTIVE",
            "FROZEN",
        }:
            return error(
                "You already have an active debit card.",
                409,
            )

    card = bank.create_card(
        account,
        status="ISSUED",
    )

    if not bank.save_data():
        account["cards"].remove(card)

        return error(
            "Card creation failed. No changes were saved.",
            500,
        )

    create_notification(
        account,
        "info",
        "Debit card issued",
        (
            f"Your BlueBank debit card ending in "
            f"{card['last_four']} has been issued."
        ),
    )

    bank.save_data()

    return jsonify({
        "success": True,
        "message": "Debit card issued successfully.",
        "card": bank.public_card(card),
    }), 201

@app.patch("/api/cards/<card_id>/freeze")
def freeze_card(card_id):
    account = authenticated_account()

    if account is None:
        return error("Please login first.", 401)

    card = next(
        (
            item
            for item in account.get("cards", [])
            if item.get("id") == card_id
        ),
        None,
    )

    if card is None:
        return error("Card not found.", 404)

    bank.refresh_card_status(card)

    if card.get("status") == "BLOCKED":
        return error("Blocked cards cannot be frozen.", 400)

    if card.get("status") == "FROZEN":
        return error("Card is already frozen.", 400)

    if card.get("status") == "EXPIRED":
        return error("Expired cards cannot be modified.", 400)

    card["status"] = "FROZEN"

    if not bank.save_data():
        card["status"] = "ACTIVE"

        return error(
            "Card freeze failed. No changes were saved.",
            500,
        )

    create_notification(
        account,
        "warning",
        "Card frozen",
        f"Your debit card ending in {card['last_four']} has been frozen.",
    )

    bank.save_data()

    return jsonify({
        "success": True,
        "message": "Card frozen successfully.",
        "card": bank.public_card(card),
    })

@app.patch("/api/cards/<card_id>/unfreeze")
def unfreeze_card(card_id):
    account = authenticated_account()

    if account is None:
        return error("Please login first.", 401)

    card = next(
        (
            item
            for item in account.get("cards", [])
            if item.get("id") == card_id
        ),
        None,
    )

    if card is None:
        return error("Card not found.", 404)

    bank.refresh_card_status(card)

    if card.get("status") == "BLOCKED":
        return error("Blocked cards cannot be unfrozen.", 400)

    if card.get("status") == "ACTIVE":
        return error("Card is already active.", 400)

    if card.get("status") == "EXPIRED":
        return error("Expired cards cannot be modified.", 400)

    card["status"] = "ACTIVE"

    if not bank.save_data():
        card["status"] = "FROZEN"

        return error(
            "Card unfreeze failed. No changes were saved.",
            500,
        )

    create_notification(
        account,
        "success",
        "Card unfrozen",
        f"Your debit card ending in {card['last_four']} is active again.",
    )

    bank.save_data()

    return jsonify({
        "success": True,
        "message": "Card unfrozen successfully.",
        "card": bank.public_card(card),
    })

@app.patch("/api/cards/<card_id>/limit")
def update_card_limit(card_id):
    account = authenticated_account()

    if account is None:
        return error("Please login first.", 401)

    card = next(
        (
            item
            for item in account.get("cards", [])
            if item.get("id") == card_id
        ),
        None,
    )

    if card is None:
        return error("Card not found.", 404)

    data = request_json()

    if data is None:
        return error("A JSON request body is required.")

    amount = bank.parse_amount(data.get("daily_limit"))

    if amount is None:
        return error(
            "Enter a valid daily spending limit."
        )

    if amount < 100:
        return error(
            "Daily spending limit must be at least $100."
        )

    if amount > 10000:
        return error(
            "Daily spending limit cannot exceed $10,000."
        )

    old_limit = card["daily_limit"]
    card["daily_limit"] = str(amount.quantize(Decimal("0.01")))

    if not bank.save_data():
        card["daily_limit"] = old_limit

        return error(
            "Limit update failed. No changes were saved.",
            500,
        )

    create_notification(
        account,
        "info",
        "Card limit updated",
        (
            f"Your card ending in {card['last_four']} "
            f"now has a daily spending limit of "
            f"${card['daily_limit']}."
        ),
    )

    bank.save_data()

    return jsonify({
        "success": True,
        "message": "Daily spending limit updated successfully.",
        "card": bank.public_card(card),
    })

@app.patch("/api/cards/<card_id>/activate")
def activate_card(card_id):
    account = authenticated_account()

    if account is None:
        return error("Please login first.", 401)

    card = next(
        (
            item
            for item in account.get("cards", [])
            if item.get("id") == card_id
        ),
        None,
    )

    if card is None:
        return error("Card not found.", 404)

    bank.refresh_card_status(card)

    if card.get("status") == "EXPIRED":
        return error(
            "This card has expired.",
            400,
        )

    if card.get("status") != "ISSUED":
        return error(
            "Only issued cards can be activated.",
            400,
        )

    card["status"] = "ACTIVE"

    if not bank.save_data():
        card["status"] = "ISSUED"

        return error(
            "Card activation failed.",
            500,
        )

    create_notification(
        account,
        "success",
        "Card activated",
        (
            f"Your debit card ending in "
            f"{card['last_four']} is now active."
        ),
    )

    bank.save_data()

    return jsonify({
        "success": True,
        "message": "Card activated successfully.",
        "card": bank.public_card(card),
    })

@app.patch("/api/cards/<card_id>/block")
def block_card(card_id):
    account = authenticated_account()

    if account is None:
        return error("Please login first.", 401)

    card = next(
        (
            item
            for item in account.get("cards", [])
            if item.get("id") == card_id
        ),
        None,
    )

    if card is None:
        return error("Card not found.", 404)

    if card.get("status") == "BLOCKED":
        return error(
            "Card is already blocked.",
            400,
        )

    if card.get("status") == "REPLACED":
        return error(
            "This card has already been replaced.",
            400,
        )

    card["status"] = "BLOCKED"

    if not bank.save_data():
        return error(
            "Card blocking failed.",
            500,
        )

    create_notification(
        account,
        "warning",
        "Card blocked",
        (
            f"Your debit card ending in "
            f"{card['last_four']} has been permanently blocked."
        ),
    )

    bank.save_data()

    return jsonify({
        "success": True,
        "message": "Card blocked successfully.",
        "card": bank.public_card(card),
    })

@app.post("/api/cards/<card_id>/replace")
def replace_card(card_id):
    account = authenticated_account()

    if account is None:
        return error("Please login first.", 401)

    old_card = next(
        (
            item
            for item in account.get("cards", [])
            if item.get("id") == card_id
        ),
        None,
    )

    if old_card is None:
        return error("Card not found.", 404)

    if old_card.get("status") == "REPLACED":
        return error(
            "This card has already been replaced.",
            400,
        )

    if old_card.get("status") == "BLOCKED":
        return error(
            "Blocked card cannot be replaced.",
            400,
        )

    old_card["status"] = "REPLACED"

    new_card = bank.create_card(
        account,
        status="ISSUED",
    )

    if not bank.save_data():
        old_card["status"] = "ACTIVE"
        account["cards"].remove(new_card)

        return error(
            "Card replacement failed.",
            500,
        )

    create_notification(
        account,
        "info",
        "Card replaced",
        (
            f"Your old card ending in "
            f"{old_card['last_four']} was replaced. "
            f"New card ending in "
            f"{new_card['last_four']} is ready for activation."
        ),
    )

    bank.save_data()

    return jsonify({
        "success": True,
        "message": "Replacement card issued successfully.",
        "old_card": bank.public_card(old_card),
        "card": bank.public_card(new_card),
    }), 201

@app.post("/api/cards/virtual")
def create_virtual_card():
    account = authenticated_account()

    if account is None:
        return error("Please login first.", 401)

    active_virtual_cards = [
        card
        for card in account.get(
            "virtual_cards",
            [],
        )
        if card.get("status") == "ACTIVE"
    ]

    if active_virtual_cards:
        return error(
            "You already have an active virtual card.",
            409,
        )

    card = bank.create_virtual_card(account)

    if not bank.save_data():
        account["virtual_cards"].remove(card)

        return error(
            "Virtual card creation failed.",
            500,
        )

    create_notification(
        account,
        "success",
        "Virtual card created",
        (
            f"Your virtual card ending in "
            f"{card['last_four']} is now active."
        ),
    )

    bank.save_data()

    return jsonify({
        "success": True,
        "message": "Virtual card created successfully.",
        "card": bank.public_virtual_card(card),
    }), 201

@app.put("/api/profile")
def update_profile():
    account = authenticated_account()

    if account is None:
        return error("Please login first.", 401)

    data = request_json()

    if data is None:
        return error("A JSON request body is required.")

    email = data.get("email")

    if not isinstance(email, str):
        return error("Email address is required.")

    email = email.strip().lower()

    if not email:
        return error("Email address is required.")

    if len(email) > 254:
        return error("Email address is too long.")

    if not re.fullmatch(
        r"[A-Za-z0-9.!#$%&'*+/=?^_`{|}~-]+"
        r"@[A-Za-z0-9-]+(?:\.[A-Za-z0-9-]+)+",
        email,
    ):
        return error("Enter a valid email address.")

    old_email = account.get("email", "")

    account["email"] = email

    if not bank.save_data():
        account["email"] = old_email

        return error(
            "Profile update failed. No changes were saved.",
            500,
        )

    return jsonify({
        "success": True,
        "message": "Email address updated successfully.",
        "account": bank.public_account(account),
    })

@app.get("/api/balance")
def balance():
    account = authenticated_account()

    if account is None:
        return error("Please login first.", 401)

    return jsonify({
        "success": True,
        "balance": str(account["balance"]),
        "currency": "USD"
    })


def append_transaction(
    account,
    transaction_type,
    amount,
    status="COMPLETED",
    **details,
):
    transaction = {
        "id": (
            "TXN-" + secrets.token_hex(8).upper()
        ),
        "type": transaction_type,
        "amount": str(amount),
        "status": status,
        "balance_after": str(account["balance"]),
        "created_at": datetime.now(timezone.utc).isoformat(),
    }
    transaction.update(details)

    account.setdefault("transactions", []).insert(
        0,
        transaction
    )

    return transaction


def record_failed_transaction(
    account,
    transaction_type,
    amount,
    reason,
    **details,
):
    transaction = append_transaction(
        account,
        transaction_type,
        amount,
        status="FAILED",
        failure_reason=reason,
        **details,
    )
    if not bank.save_data():
        return None
    return transaction


@app.post("/api/deposit")
def deposit():
    account = authenticated_account()

    if account is None:
        return error("Please login first.", 401)

    data = request_json()

    if data is None:
        return error("A JSON request body is required.")

    amount = bank.parse_amount(data.get("amount"))

    if amount is None:
        return error(
            "Enter an amount greater than zero "
            "with up to 2 decimal places."
        )

    if amount > MAX_TRANSACTION_AMOUNT:
        return error(
            "Transaction amount cannot exceed 500 crore."
        )

    old_balance = account["balance"]
    old_transactions = list(
        account.get("transactions", [])
    )
    old_notifications = list(
        account.get("notifications", [])
    )

    account["balance"] += amount

    transaction = append_transaction(
        account,
        "DEPOSIT",
        amount
    )
    create_transaction_alerts(account, transaction, old_balance)

    create_notification(
        account,
        "SUCCESS",
        "Deposit successful",
        f"Successfully deposited ${amount:.2f} into your account."
    )

    if not bank.save_data():
        account["balance"] = old_balance
        account["transactions"] = old_transactions
        account["notifications"] = old_notifications

        return error(
            "Deposit failed. No changes were saved.",
            500
        )

    return jsonify({
        "success": True,
        "message": f"Successfully deposited ${amount:.2f}.",
        "balance": str(account["balance"]),
        "transaction": transaction,
    })


@app.post("/api/withdraw")
def withdraw():
    account = authenticated_account()

    if account is None:
        return error("Please login first.", 401)

    data = request_json()

    if data is None:
        return error("A JSON request body is required.")

    amount = bank.parse_amount(data.get("amount"))

    if amount is None:
        return error(
            "Enter an amount greater than zero "
            "with up to 2 decimal places."
        )

    if amount > MAX_TRANSACTION_AMOUNT:
        return error(
            "Transaction amount cannot exceed 500 crore."
        )

    if amount > bank.available_balance(account):
        if record_failed_transaction(
            account,
            "WITHDRAW",
            amount,
            "Insufficient available funds",
        ) is None:
            return error("Could not save the failed withdrawal record.", 503)
        return error("Insufficient available funds.")

    old_balance = account["balance"]
    old_transactions = list(
        account.get("transactions", [])
    )
    old_notifications = list(
        account.get("notifications", [])
    )

    account["balance"] -= amount

    transaction = append_transaction(
        account,
        "WITHDRAW",
        amount
    )
    create_transaction_alerts(account, transaction, old_balance)

    create_notification(
        account,
        "SUCCESS",
        "Withdrawal successful",
        f"Successfully withdrew ${amount:.2f} from your account."
    )

    if not bank.save_data():
        account["balance"] = old_balance
        account["transactions"] = old_transactions
        account["notifications"] = old_notifications

        return error(
            "Withdrawal failed. No changes were saved.",
            500
        )

    return jsonify({
        "success": True,
        "message": f"Successfully withdrew ${amount:.2f}.",
        "balance": str(account["balance"]),
        "transaction": transaction,
    })


@app.get("/api/transactions")
def transaction_history():
    account = authenticated_account()

    if account is None:
        return error("Please login first.", 401)

    transactions = account.get("transactions", [])

    return jsonify({
        "success": True,
        "transactions": transactions
    })


@app.patch("/api/transactions/<transaction_id>/category")
def update_transaction_category(transaction_id):
    account = authenticated_account()
    if account is None:
        return error("Please login first.", 401)
    data = request_json()
    if data is None:
        return error("A JSON request body is required.")
    category = data.get("category")
    if category not in SPENDING_CATEGORIES:
        return error("Choose a supported spending category.")
    transaction = next(
        (
            item
            for item in account.get("transactions", [])
            if item.get("id") == transaction_id
        ),
        None,
    )
    if transaction is None:
        return error("Transaction not found.", 404)
    old_category = transaction.get("category")
    transaction["category"] = category
    if not bank.save_data():
        if old_category is None:
            transaction.pop("category", None)
        else:
            transaction["category"] = old_category
        return error("Could not update the transaction category.", 503)
    return jsonify({"success": True, "transaction": transaction})


@app.post("/api/change-pin")
def change_pin():
    account = authenticated_account()

    if account is None:
        return error("Please login first.", 401)

    data = request_json()

    if data is None:
        return error("A JSON request body is required.")

    current_pin = data.get("current_pin")
    new_pin = data.get("new_pin")

    lock_response = pin_lock_response(account)
    if lock_response is not None:
        return lock_response
    if not account_pin_matches(account, current_pin):
        return record_failed_pin_attempt(account)

    if (
        not isinstance(new_pin, str)
        or not bank.is_strong_pin(new_pin)
    ):
        return error(
            "Choose a valid, strong 4-digit PIN."
        )

    if bank.verify_pin(
        new_pin,
        account["pin_salt"],
        account["pin_hash"]
    ):
        return error(
            "New PIN cannot be the same as the current PIN."
        )

    old_salt = account["pin_salt"]
    old_hash = account["pin_hash"]
    old_failed_attempts = account.get("failed_attempts", 0)
    old_locked_until = account.get("locked_until", 0)
    clear_pin_failures(account)

    account["pin_salt"], account["pin_hash"] = (
        bank.hash_pin(new_pin)
    )

    if not bank.save_data():
        account["pin_salt"] = old_salt
        account["pin_hash"] = old_hash
        account["failed_attempts"] = old_failed_attempts
        account["locked_until"] = old_locked_until

        return error(
            "PIN update failed. No changes were saved.",
            500
        )

    return jsonify({
        "success": True,
        "message": "PIN changed successfully."
    })


def find_beneficiary(account, beneficiary_id):
    return next(
        (
            item
            for item in account.get("beneficiaries", [])
            if item.get("beneficiary_id") == beneficiary_id
        ),
        None
    )


@app.get("/api/beneficiaries")
def get_beneficiaries():
    account = authenticated_account()

    if account is None:
        return error("Please login first.", 401)

    return jsonify({
        "success": True,
        "beneficiaries": account.get("beneficiaries", [])
    })


@app.post("/api/beneficiaries")
def add_beneficiary():
    account = authenticated_account()

    if account is None:
        return error("Please login first.", 401)

    data = request_json()

    if data is None:
        return error("A JSON request body is required.")

    account_number = str(
        data.get("account_number", "")
    ).strip()

    if not re.fullmatch(r"[0-9]{11}", account_number):
        return error(
            "Enter a valid 11-digit account number."
        )

    if account_number == account["account_number"]:
        return error(
            "You cannot add your own account as a beneficiary."
        )

    recipient = bank.accounts.get(account_number)

    if recipient is None:
        return error(
            "BlueBank account not found.",
            404
        )

    name = data.get("name")

    if (
        not isinstance(name, str)
        or name.strip().casefold()
        != recipient["name"].casefold()
    ):
        return error(
            "Beneficiary name does not match the account holder."
        )

    beneficiaries = account.setdefault(
        "beneficiaries",
        []
    )

    if any(
        item.get("account_number") == account_number
        for item in beneficiaries
    ):
        return error(
            "This beneficiary is already saved.",
            409
        )

    beneficiary = {
        "beneficiary_id": (
            "BEN-" + secrets.token_hex(6).upper()
        ),
        "name": recipient["name"],
        "account_number": account_number,
        "created_at": datetime.now(
            timezone.utc
        ).isoformat()
    }

    beneficiaries.append(beneficiary)

    if not bank.save_data():
        beneficiaries.pop()

        return error(
            "Could not save beneficiary.",
            500
        )

    return jsonify({
        "success": True,
        "message": "Beneficiary added successfully.",
        "beneficiary": beneficiary
    }), 201


@app.put("/api/beneficiaries/<beneficiary_id>")
def update_beneficiary(beneficiary_id):
    account = authenticated_account()

    if account is None:
        return error("Please login first.", 401)

    data = request_json()

    if data is None:
        return error("A JSON request body is required.")

    beneficiary = find_beneficiary(
        account,
        beneficiary_id
    )

    if beneficiary is None:
        return error(
            "Beneficiary not found.",
            404
        )

    new_account_number = str(
        data.get("account_number", "")
    ).strip()

    if not re.fullmatch(
        r"[0-9]{11}",
        new_account_number
    ):
        return error(
            "Enter a valid 11-digit account number."
        )

    if new_account_number == account["account_number"]:
        return error(
            "You cannot add your own account as a beneficiary."
        )

    recipient = bank.accounts.get(
        new_account_number
    )

    if recipient is None:
        return error(
            "BlueBank account not found.",
            404
        )

    name = data.get("name")

    if (
        not isinstance(name, str)
        or name.strip().casefold()
        != recipient["name"].casefold()
    ):
        return error(
            "Beneficiary name does not match the account holder."
        )

    if any(
        item["beneficiary_id"] != beneficiary_id
        and item.get("account_number") == new_account_number
        for item in account.get("beneficiaries", [])
    ):
        return error(
            "This beneficiary is already saved.",
            409
        )

    old_values = beneficiary.copy()

    beneficiary["name"] = recipient["name"]
    beneficiary["account_number"] = new_account_number

    if not bank.save_data():
        beneficiary.update(old_values)

        return error(
            "Could not update beneficiary.",
            500
        )

    return jsonify({
        "success": True,
        "message": "Beneficiary updated successfully.",
        "beneficiary": beneficiary
    })


@app.delete("/api/beneficiaries/<beneficiary_id>")
def delete_beneficiary(beneficiary_id):
    account = authenticated_account()

    if account is None:
        return error("Please login first.", 401)

    beneficiary = find_beneficiary(
        account,
        beneficiary_id
    )

    if beneficiary is None:
        return error(
            "Beneficiary not found.",
            404
        )

    beneficiaries = account.get(
        "beneficiaries",
        []
    )

    index = beneficiaries.index(
        beneficiary
    )

    beneficiaries.pop(index)

    if not bank.save_data():
        beneficiaries.insert(
            index,
            beneficiary
        )

        return error(
            "Could not delete beneficiary.",
            500
        )

    return jsonify({
        "success": True,
        "message": "Beneficiary deleted successfully."
    })


@app.post("/api/transfer")
def transfer_funds():
    account = authenticated_account()

    if account is None:
        return error("Please login first.", 401)

    data = request_json()

    if data is None:
        return error("A JSON request body is required.")

    raw_beneficiary_id = data.get("beneficiary_id")
    if not isinstance(raw_beneficiary_id, str) or not raw_beneficiary_id.strip():
        return error("Choose a valid beneficiary.")
    beneficiary_id = raw_beneficiary_id.strip()

    pin = data.get("pin")
    amount = bank.parse_amount(
        data.get("amount")
    )

    if amount is None or amount <= 0:
        return error(
            "Enter a valid transfer amount."
        )

    if amount > MAX_TRANSACTION_AMOUNT:
        return error(
            "Transaction amount cannot exceed 500 crore."
        )

    if (
        not isinstance(pin, str)
        or not bank.is_strong_pin(pin)
    ):
        return error(
            "Enter a valid 4-digit PIN."
        )

    lock_response = pin_lock_response(account)
    if lock_response is not None:
        return lock_response
    if not account_pin_matches(account, pin):
        return record_failed_pin_attempt(account)

    previous_failed_attempts = account.get("failed_attempts", 0)
    previous_locked_until = account.get("locked_until", 0)
    clear_pin_failures(account)

    beneficiary = find_beneficiary(
        account,
        beneficiary_id
    )

    if beneficiary is None:
        return error(
            "Beneficiary not found.",
            404
        )

    recipient_account_number = beneficiary["account_number"]
    recipient = (
        bank.refresh_account(recipient_account_number)
        if session.get("server_session_id")
        else bank.accounts.get(recipient_account_number)
    )

    if recipient is None:
        return error(
            "Beneficiary account no longer exists.",
            404
        )

    if bank.available_balance(account) < amount:
        if record_failed_transaction(
            account,
            "TRANSFER",
            amount,
            "Insufficient available funds",
            recipient_account=recipient["account_number"],
        ) is None:
            return error("Could not save the failed transfer record.", 503)
        return error("Insufficient available funds.", 400)

    old_sender_balance = account["balance"]
    old_recipient_balance = recipient["balance"]

    old_sender_transactions = list(
        account.get("transactions", [])
    )

    old_recipient_transactions = list(
        recipient.get("transactions", [])
    )

    old_sender_notifications = list(
        account.get("notifications", [])
    )

    old_recipient_notifications = list(
        recipient.get("notifications", [])
    )

    new_sender_balance = (
        old_sender_balance - amount
    )

    new_recipient_balance = (
        old_recipient_balance + amount
    )

    reference = (
        "TRF-" + secrets.token_hex(6).upper()
    )

    created_at = datetime.now(
        timezone.utc
    ).isoformat()

    sender_transaction = {
        "id": reference,
        "type": "TRANSFER",
        "amount": str(amount),
        "status": "COMPLETED",
        "balance_after": str(new_sender_balance),
        "created_at": created_at,
        "reference": reference,
        "description": (
            f"Transfer to {recipient['name']}"
        ),
        "recipient_account": (
            recipient["account_number"]
        )
    }

    recipient_transaction = {
        "id": reference,
        "type": "TRANSFER_RECEIVED",
        "amount": str(amount),
        "status": "COMPLETED",
        "balance_after": str(new_recipient_balance),
        "created_at": created_at,
        "reference": reference,
        "description": (
            f"Transfer from {account['name']}"
        ),
        "sender_account": (
            account["account_number"]
        )
    }

    account["balance"] = new_sender_balance
    recipient["balance"] = new_recipient_balance

    account.setdefault(
        "transactions",
        []
    ).insert(
        0,
        sender_transaction
    )

    recipient.setdefault(
        "transactions",
        []
    ).insert(
        0,
        recipient_transaction
    )

    if should_send_transfer_notification(account):
        create_notification(
            account,
            "SUCCESS",
            "Transfer successful",
            (
                f"${amount:.2f} sent to "
                f"{recipient['name']}."
            )
        )

    if should_send_transfer_notification(recipient):
        create_notification(
            recipient,
            "SUCCESS",
            "Money received",
            (
                f"You received ${amount:.2f} "
                f"from {account['name']}."
            )
        )

    create_transaction_alerts(
        account,
        sender_transaction,
        old_sender_balance,
    )
    create_transaction_alerts(
        recipient,
        recipient_transaction,
        old_recipient_balance,
    )

    try:
        bank.save_accounts_atomic([
            account["account_number"],
            recipient["account_number"],
        ])
    except Exception:
        logger.exception("Atomic transfer persistence failed")
        account["balance"] = old_sender_balance
        recipient["balance"] = old_recipient_balance
        account["failed_attempts"] = previous_failed_attempts
        account["locked_until"] = previous_locked_until

        account["transactions"] = (
            old_sender_transactions
        )

        recipient["transactions"] = (
            old_recipient_transactions
        )

        account["notifications"] = (
            old_sender_notifications
        )

        recipient["notifications"] = (
            old_recipient_notifications
        )

        return error(
            "Transfer failed because the account data could not be committed. No money was transferred.",
            503
        )

    return jsonify({
        "success": True,
        "message": "Fund transfer completed successfully.",
        "transfer": {
            "reference": reference,
            "amount": str(amount),
            "recipient_name": recipient["name"],
            "recipient_account": recipient["account_number"],
            "sender_balance": str(new_sender_balance),
            "created_at": created_at
        }
    }), 200


def _next_schedule_occurrence(value, frequency, now, day_of_month=None):
    scheduled_at = datetime.fromisoformat(value)
    if day_of_month is None:
        day_of_month = scheduled_at.day
    while scheduled_at <= now:
        if frequency == "WEEKLY":
            scheduled_at += timedelta(days=7)
        elif frequency == "MONTHLY":
            next_month = scheduled_at.month % 12 + 1
            next_year = scheduled_at.year + (scheduled_at.month // 12)
            scheduled_at = scheduled_at.replace(
                year=next_year,
                month=next_month,
                day=min(day_of_month, calendar.monthrange(next_year, next_month)[1]),
            )
        else:
            raise ValueError(f"Unsupported recurring frequency: {frequency}")
    return scheduled_at


def _public_schedule(schedule):
    return {
        key: schedule.get(key)
        for key in (
            "id",
            "beneficiary_id",
            "recipient_account",
            "recipient_name",
            "amount",
            "frequency",
            "status",
            "next_run_at",
            "last_run_at",
            "created_at",
            "transaction_id",
        )
    }


@app.get("/api/scheduled-transfers")
def get_scheduled_transfers():
    account = authenticated_account()
    if account is None:
        return error("Please login first.", 401)

    schedules = list(
        bank.scheduled_transfers_collection.find(
            {"account_number": account["account_number"]},
            {"_id": 0, "claim_token": 0, "claim_until": 0},
        ).sort("created_at", -1)
    )
    return jsonify({"success": True, "scheduled_transfers": schedules})


@app.post("/api/scheduled-transfers")
def create_scheduled_transfer():
    account = authenticated_account()
    if account is None:
        return error("Please login first.", 401)

    data = request_json()
    if data is None:
        return error("A JSON request body is required.")

    raw_beneficiary_id = data.get("beneficiary_id")
    if not isinstance(raw_beneficiary_id, str) or not raw_beneficiary_id.strip():
        return error("Choose a valid beneficiary.")
    beneficiary_id = raw_beneficiary_id.strip()
    raw_frequency = data.get("frequency", "ONCE")
    if not isinstance(raw_frequency, str):
        return error("Choose a supported transfer frequency.")
    frequency = raw_frequency.upper()
    scheduled_for = data.get("scheduled_for")
    pin = data.get("pin")
    amount = bank.parse_amount(data.get("amount"))
    if amount is None:
        return error("Enter a valid transfer amount.")
    if amount > MAX_TRANSACTION_AMOUNT:
        return error("Transaction amount cannot exceed 500 crore.")
    if frequency not in {"ONCE", "WEEKLY", "MONTHLY"}:
        return error("Choose a supported transfer frequency.")
    if not isinstance(scheduled_for, str) or not scheduled_for:
        return error("Choose a valid scheduled date and time.")
    if not isinstance(pin, str) or not re.fullmatch(r"[0-9]{4}", pin):
        return error("Enter a valid 4-digit PIN.")
    lock_response = pin_lock_response(account)
    if lock_response is not None:
        return lock_response
    if not account_pin_matches(account, pin):
        return record_failed_pin_attempt(account)

    previous_failed_attempts = account.get("failed_attempts", 0)
    previous_locked_until = account.get("locked_until", 0)
    clear_pin_failures(account)

    try:
        next_run = datetime.fromisoformat(scheduled_for)
        if next_run.tzinfo is None:
            next_run = next_run.replace(tzinfo=timezone.utc)
        next_run = next_run.astimezone(timezone.utc)
    except (TypeError, ValueError):
        return error("Choose a valid scheduled date and time.")
    now = datetime.now(timezone.utc)
    if next_run <= now:
        return error("The scheduled date and time must be in the future.")

    beneficiary = find_beneficiary(account, beneficiary_id)
    if beneficiary is None:
        return error("Beneficiary not found.", 404)

    recipient_account_number = beneficiary["account_number"]
    recipient = (
        bank.refresh_account(recipient_account_number)
        if session.get("server_session_id")
        else bank.accounts.get(recipient_account_number)
    )
    if recipient is None:
        return error("Beneficiary account no longer exists.", 404)
    if amount > bank.available_balance(account):
        return error("Insufficient available funds for this transfer.")

    schedule_id = "SCH-" + secrets.token_hex(8).upper()
    transaction = append_transaction(
        account,
        "SCHEDULED_TRANSFER",
        amount,
        status="PENDING",
        schedule_id=schedule_id,
        reference=schedule_id,
        description=f"Scheduled transfer to {recipient['name']}",
        recipient_account=recipient_account_number,
    )
    schedule = {
        "id": schedule_id,
        "account_number": account["account_number"],
        "beneficiary_id": beneficiary_id,
        "recipient_account": recipient_account_number,
        "recipient_name": recipient["name"],
        "amount": str(amount),
        "frequency": frequency,
        "day_of_month": next_run.day if frequency == "MONTHLY" else None,
        "status": "ACTIVE",
        "next_run_at": next_run.isoformat(),
        "last_run_at": None,
        "created_at": now.isoformat(),
        "transaction_id": transaction["id"],
    }

    try:
        with bank.mongo_client.start_session() as mongo_session:
            with mongo_session.start_transaction():
                bank.save_accounts_atomic(
                    [account["account_number"]],
                    session=mongo_session,
                )
                bank.scheduled_transfers_collection.insert_one(
                    schedule,
                    session=mongo_session,
                )
        bank.mark_accounts_persisted([account["account_number"]])
    except Exception:
        account["transactions"].remove(transaction)
        account["failed_attempts"] = previous_failed_attempts
        account["locked_until"] = previous_locked_until
        logger.exception("Could not save scheduled transfer")
        return error("Could not schedule this transfer. No changes were saved.", 503)

    return jsonify({
        "success": True,
        "message": "Transfer scheduled successfully.",
        "scheduled_transfer": _public_schedule(schedule),
    }), 201


@app.delete("/api/scheduled-transfers/<schedule_id>")
def cancel_scheduled_transfer(schedule_id):
    account = authenticated_account()
    if account is None:
        return error("Please login first.", 401)

    schedule = bank.scheduled_transfers_collection.find_one({
        "id": schedule_id,
        "account_number": account["account_number"],
        "status": "ACTIVE",
    })
    if schedule is None:
        return error("Active scheduled transfer not found.", 404)
    if schedule.get("claim_until", "") > datetime.now(timezone.utc).isoformat():
        return error("This transfer is currently being processed.", 409)

    transaction = next(
        (
            item
            for item in account.get("transactions", [])
            if item.get("id") == schedule.get("transaction_id")
        ),
        None,
    )
    if transaction is None:
        return error("Scheduled transfer history is unavailable.", 409)

    old_status = transaction.get("status")
    transaction["status"] = "CANCELLED"
    try:
        with bank.mongo_client.start_session() as mongo_session:
            with mongo_session.start_transaction():
                bank.save_accounts_atomic(
                    [account["account_number"]],
                    session=mongo_session,
                )
                result = bank.scheduled_transfers_collection.update_one(
                    {
                        "id": schedule_id,
                        "account_number": account["account_number"],
                        "status": "ACTIVE",
                        "$or": [
                            {"claim_until": {"$exists": False}},
                            {"claim_until": {"$lte": datetime.now(timezone.utc).isoformat()}},
                        ],
                    },
                    {"$set": {"status": "CANCELLED"}},
                    session=mongo_session,
                )
                if result.matched_count != 1:
                    raise bank.ConcurrentAccountWriteError(
                        "Scheduled transfer was claimed by a worker."
                    )
        bank.mark_accounts_persisted([account["account_number"]])
    except Exception:
        transaction["status"] = old_status
        logger.exception("Could not cancel scheduled transfer")
        return error("Could not cancel this transfer. Please try again.", 409)

    return jsonify({"success": True, "message": "Scheduled transfer cancelled."})


def process_due_scheduled_transfers(batch_size=25):
    bank.load_data()
    if not bank.storage_ready:
        raise RuntimeError("Account storage is unavailable to the scheduler.")

    now = datetime.now(timezone.utc)
    now_text = now.isoformat()
    processed = 0
    for _ in range(batch_size):
        claim_token = secrets.token_urlsafe(24)
        schedule = bank.scheduled_transfers_collection.find_one_and_update(
            {
                "status": "ACTIVE",
                "next_run_at": {"$lte": now_text},
                "$or": [
                    {"claim_until": {"$exists": False}},
                    {"claim_until": {"$lte": now_text}},
                ],
            },
            {
                "$set": {
                    "claim_token": claim_token,
                    "claim_until": (now + timedelta(minutes=5)).isoformat(),
                }
            },
            sort=[("next_run_at", 1)],
            return_document=ReturnDocument.AFTER,
        )
        if schedule is None:
            break
        try:
            _process_claimed_scheduled_transfer(schedule, claim_token, now)
            processed += 1
        except Exception:
            logger.exception(
                "Scheduled transfer %s could not be processed",
                schedule.get("id"),
            )
            bank.scheduled_transfers_collection.update_one(
                {"id": schedule.get("id"), "claim_token": claim_token},
                {"$unset": {"claim_token": "", "claim_until": ""}},
            )
            raise
    return processed


def _process_claimed_scheduled_transfer(schedule, claim_token, now):
    account_number = schedule["account_number"]
    account = bank.refresh_account(account_number)
    if account is None:
        raise RuntimeError("Scheduled transfer source account was not found.")

    recipient_number = schedule["recipient_account"]
    recipient = bank.refresh_account(recipient_number)
    amount = Decimal(str(schedule["amount"]))
    transaction = next(
        (
            item
            for item in account.get("transactions", [])
            if item.get("id") == schedule.get("transaction_id")
        ),
        None,
    )
    if transaction is None:
        raise RuntimeError("Scheduled transfer transaction was not found.")

    sender_balance = account["balance"]
    original_account_transactions = copy.deepcopy(account.get("transactions", []))
    original_account_notifications = copy.deepcopy(account.get("notifications", []))
    successful = (
        recipient is not None
        and bank.available_balance(account) >= amount
    )
    account_numbers = [account_number]

    if successful:
        recipient_balance = recipient["balance"]
        original_recipient_transactions = copy.deepcopy(
            recipient.get("transactions", [])
        )
        original_recipient_notifications = copy.deepcopy(
            recipient.get("notifications", [])
        )
        account_numbers.append(recipient_number)
        account["balance"] -= amount
        recipient["balance"] += amount
        transaction["type"] = "TRANSFER"
        transaction["status"] = "COMPLETED"
        transaction["balance_after"] = str(account["balance"])
        transaction["created_at"] = now.isoformat()
        recipient_transaction = {
            "id": transaction["id"],
            "type": "TRANSFER_RECEIVED",
            "amount": str(amount),
            "status": "COMPLETED",
            "balance_after": str(recipient["balance"]),
            "created_at": now.isoformat(),
            "reference": schedule["id"],
            "description": f"Scheduled transfer from {account['name']}",
            "sender_account": account_number,
        }
        recipient.setdefault("transactions", []).insert(
            0,
            recipient_transaction,
        )
        if should_send_transfer_notification(account):
            create_notification(
                account,
                "SUCCESS",
                "Scheduled transfer sent",
                f"${amount:.2f} was sent to {recipient['name']}.",
            )
        if should_send_transfer_notification(recipient):
            create_notification(
                recipient,
                "SUCCESS",
                "Money received",
                f"You received ${amount:.2f} from {account['name']}.",
            )
        create_transaction_alerts(account, transaction, sender_balance)
        create_transaction_alerts(
            recipient,
            recipient_transaction,
            recipient_balance,
        )
    else:
        transaction["type"] = "TRANSFER"
        transaction["status"] = "FAILED"
        transaction["failure_reason"] = (
            "Recipient account unavailable"
            if recipient is None
            else "Insufficient available funds"
        )
        transaction["balance_after"] = str(account["balance"])
        if should_send_transfer_notification(account):
            create_notification(
                account,
                "ERROR",
                "Scheduled transfer failed",
                f"The scheduled ${amount:.2f} transfer could not be completed.",
            )

    recurring = schedule["frequency"] in {"WEEKLY", "MONTHLY"}
    schedule_update = {
        "last_run_at": now.isoformat(),
        "status": (
            "ACTIVE" if recurring and successful else
            "ACTIVE" if recurring else
            "COMPLETED" if successful else
            "FAILED"
        ),
    }
    if recurring:
        next_run = _next_schedule_occurrence(
            schedule["next_run_at"],
            schedule["frequency"],
            now,
            schedule.get("day_of_month"),
        )
        schedule_update["next_run_at"] = next_run.isoformat()
        next_transaction = {
            "id": "TXN-" + secrets.token_hex(8).upper(),
            "type": "SCHEDULED_TRANSFER",
            "amount": str(amount),
            "status": "PENDING",
            "balance_after": str(account["balance"]),
            "created_at": now.isoformat(),
            "schedule_id": schedule["id"],
            "reference": schedule["id"],
            "description": f"Scheduled transfer to {schedule['recipient_name']}",
            "recipient_account": recipient_number,
        }
        account.setdefault("transactions", []).insert(0, next_transaction)
        schedule_update["transaction_id"] = next_transaction["id"]

    try:
        with bank.mongo_client.start_session() as mongo_session:
            with mongo_session.start_transaction():
                bank.save_accounts_atomic(
                    account_numbers,
                    session=mongo_session,
                )
                result = bank.scheduled_transfers_collection.update_one(
                    {
                        "id": schedule["id"],
                        "claim_token": claim_token,
                        "status": "ACTIVE",
                    },
                    {
                        "$set": schedule_update,
                        "$unset": {"claim_token": "", "claim_until": ""},
                    },
                    session=mongo_session,
                )
                if result.matched_count != 1:
                    raise bank.ConcurrentAccountWriteError(
                        "Scheduled transfer claim is no longer active."
                    )
        bank.mark_accounts_persisted(account_numbers)
    except Exception:
        account["balance"] = sender_balance
        account["transactions"] = original_account_transactions
        account["notifications"] = original_account_notifications
        if successful:
            recipient["balance"] = recipient_balance
            recipient["transactions"] = original_recipient_transactions
            recipient["notifications"] = original_recipient_notifications
        raise


@app.get("/api/notifications")
def get_notifications():
    account = authenticated_account()

    if account is None:
        return error("Please login first.", 401)

    notifications = account.setdefault(
        "notifications",
        []
    )

    unread_count = sum(
        1
        for notification in notifications
        if not notification.get("read", False)
    )

    return jsonify({
        "success": True,
        "notifications": notifications,
        "unread_count": unread_count,
    })


def start_scheduled_transfer_worker():
    if os.environ.get("WERKZEUG_RUN_MAIN") != "true":
        return None

    worker_path = os.path.join(
        os.path.dirname(os.path.abspath(__file__)),
        "scheduled_transfer_worker.py",
    )
    return subprocess.Popen(
        [sys.executable, worker_path],
        cwd=os.path.dirname(worker_path),
    )


@app.patch("/api/notifications/<notification_id>/read")
def mark_notification_read(notification_id):
    account = authenticated_account()

    if account is None:
        return error("Please login first.", 401)

    notification = next(
        (
            item
            for item in account.get(
                "notifications",
                []
            )
            if item.get("id") == notification_id
        ),
        None
    )

    if notification is None:
        return error(
            "Notification not found.",
            404
        )

    old_read_value = notification.get(
        "read",
        False
    )

    notification["read"] = True

    if not bank.save_data():
        notification["read"] = old_read_value

        return error(
            "Could not update notification.",
            500
        )

    return jsonify({
        "success": True,
        "message": "Notification marked as read.",
    })


@app.patch("/api/notifications/read-all")
def mark_all_notifications_read():
    account = authenticated_account()

    if account is None:
        return error("Please login first.", 401)

    notifications = account.get(
        "notifications",
        []
    )

    old_values = [
        notification.get(
            "read",
            False
        )
        for notification in notifications
    ]

    for notification in notifications:
        notification["read"] = True

    if not bank.save_data():
        for notification, old_value in zip(
            notifications,
            old_values
        ):
            notification["read"] = old_value

        return error(
            "Could not update notifications.",
            500
        )

    return jsonify({
        "success": True,
        "message": "All notifications marked as read.",
    })

@app.get("/api/security/activity")
def security_activity():
    account = authenticated_account()

    if account is None:
        return error("Please login first.", 401)

    return jsonify({
        "success": True,
        "activities": account.get(
            "security_activity",
            []
        )[:20],
    })


@app.get("/api/alerts")
def get_alert_preferences():
    account = authenticated_account()
    if account is None:
            return error("Please login first.", 401)
    preferences = account.get("alert_preferences") or bank.default_alert_preferences()
    return jsonify({"success": True, "preferences": preferences})


@app.put("/api/alerts")
def update_alert_preferences():
    account = authenticated_account()
    if account is None:
            return error("Please login first.", 401)
    data = request_json()
    if data is None:
            return error("A JSON request body is required.")

    preferences = dict(
            account.get("alert_preferences") or bank.default_alert_preferences()
    )
    for field in (
            "transaction_alerts_enabled",
            "transfer_alerts_enabled",
            "sign_in_alerts_enabled",
    ):
            if field in data:
                if not isinstance(data[field], bool):
                    return error(f"{field} must be true or false.")
                preferences[field] = data[field]

    for field in ("low_balance_threshold", "large_transaction_threshold"):
            if field not in data:
                continue
            raw_value = data[field]
            if field == "low_balance_threshold" and raw_value in (None, ""):
                preferences[field] = None
                continue
            amount = bank.parse_amount(raw_value)
            if amount is None or amount > MAX_TRANSACTION_AMOUNT:
                return error(f"Enter a valid {field.replace('_', ' ')}.")
            preferences[field] = str(amount)

    old_preferences = account.get("alert_preferences")
    account["alert_preferences"] = preferences
    if not bank.save_data():
            if old_preferences is None:
                account.pop("alert_preferences", None)
            else:
                account["alert_preferences"] = old_preferences
            return error("Could not save your alert preferences.", 503)
    return jsonify({"success": True, "preferences": preferences})


@app.get("/api/sessions")
def get_active_sessions():
    account = authenticated_account()
    if account is None:
            return error("Please login first.", 401)

    sessions = list(bank.sessions_collection.find(
            {
                "account_number": account["account_number"],
                "role": "customer",
                "revoked_at": None,
            },
            {
                "_id": 1,
                "device": 1,
                "browser": 1,
                "created_at": 1,
                "last_seen_at": 1,
            },
    ).sort("last_seen_at", -1))
    return jsonify({
            "success": True,
            "sessions": [
                {
                    "id": item["_id"],
                    "device": item.get("device", "Unknown device"),
                    "browser": item.get("browser", "Unknown browser"),
                    "created_at": item.get("created_at"),
                    "last_seen_at": item.get("last_seen_at"),
                    "current": item["_id"] == session.get("server_session_id"),
                }
                for item in sessions
            ],
    })


@app.delete("/api/sessions/<session_id>")
def revoke_session(session_id):
    account = authenticated_account()
    if account is None:
            return error("Please login first.", 401)

    result = bank.sessions_collection.update_one(
            {
                "_id": session_id,
                "account_number": account["account_number"],
                "role": "customer",
                "revoked_at": None,
            },
            {"$set": {"revoked_at": datetime.now(timezone.utc).isoformat()}},
    )
    if result.matched_count != 1:
            return error("Active session not found.", 404)

    if session_id == session.get("server_session_id"):
            session.clear()
    return jsonify({"success": True, "message": "Session revoked."})


@app.get("/api/insights")
def spending_insights():
    account = authenticated_account()
    if account is None:
            return error("Please login first.", 401)

    now = datetime.now(timezone.utc)
    categories = {}
    total = Decimal("0.00")
    for transaction in account.get("transactions", []):
            if transaction.get("status", "COMPLETED") != "COMPLETED":
                continue
            if transaction.get("type") not in {
                "WITHDRAW",
                "TRANSFER",
                "CARD_PAYMENT",
                "TRANSFER_REVERSAL_DEBIT",
            }:
                continue
            try:
                created_at = datetime.fromisoformat(transaction["created_at"])
                amount = Decimal(str(transaction["amount"]))
            except (KeyError, TypeError, ValueError, InvalidOperation):
                continue
            if (created_at.year, created_at.month) != (now.year, now.month):
                continue
            category = transaction.get("category") or "Other"
            categories[category] = categories.get(category, Decimal("0.00")) + amount
            total += amount

    budget_summary = []
    for category, budget in account.get("budgets", {}).items():
            limit = Decimal(str(budget))
            spent = categories.get(category, Decimal("0.00"))
            budget_summary.append({
                "category": category,
                "limit": str(limit),
                "spent": str(spent),
                "remaining": str(max(Decimal("0.00"), limit - spent)),
            })

    return jsonify({
            "success": True,
            "month": now.strftime("%Y-%m"),
            "total_spending": str(total),
            "categories": [
                {"category": category, "spent": str(amount)}
                for category, amount in sorted(
                    categories.items(),
                    key=lambda item: item[1],
                    reverse=True,
                )
            ],
            "budgets": budget_summary,
            "savings_goals": account.get("savings_goals", []),
            "available_balance": str(bank.available_balance(account)),
    })


@app.put("/api/budgets/<category>")
def set_spending_budget(category):
    account = authenticated_account()
    if account is None:
            return error("Please login first.", 401)
    if category not in SPENDING_CATEGORIES:
            return error("Choose a supported spending category.")
    data = request_json()
    if data is None:
            return error("A JSON request body is required.")
    amount = bank.parse_amount(data.get("amount"))
    if amount is None or amount > MAX_TRANSACTION_AMOUNT:
            return error("Enter a valid monthly budget.")

    budgets = account.setdefault("budgets", {})
    old_value = budgets.get(category)
    budgets[category] = str(amount)
    if not bank.save_data():
            if old_value is None:
                budgets.pop(category, None)
            else:
                budgets[category] = old_value
            return error("Could not save this budget.", 503)
    return jsonify({"success": True, "category": category, "amount": str(amount)})


@app.delete("/api/budgets/<category>")
def delete_spending_budget(category):
    account = authenticated_account()
    if account is None:
            return error("Please login first.", 401)
    budgets = account.get("budgets", {})
    if category not in budgets:
            return error("Budget not found.", 404)
    old_value = budgets.pop(category)
    if not bank.save_data():
            budgets[category] = old_value
            return error("Could not delete this budget.", 503)
    return jsonify({"success": True, "message": "Budget removed."})


@app.get("/api/savings-goals")
def get_savings_goals():
    account = authenticated_account()
    if account is None:
            return error("Please login first.", 401)
    return jsonify({
            "success": True,
            "goals": account.get("savings_goals", []),
            "available_balance": str(bank.available_balance(account)),
    })


@app.post("/api/savings-goals")
def create_savings_goal():
    account = authenticated_account()
    if account is None:
            return error("Please login first.", 401)
    data = request_json()
    if data is None:
            return error("A JSON request body is required.")
    name = data.get("name")
    target = bank.parse_amount(data.get("target_amount"))
    if not isinstance(name, str) or not name.strip() or len(name.strip()) > 80:
            return error("Goal name must be between 1 and 80 characters.")
    if target is None or target > MAX_TRANSACTION_AMOUNT:
            return error("Enter a valid savings target not exceeding 500 crore.")
    target_date = data.get("target_date")
    if target_date:
            if (
                not isinstance(target_date, str)
                or re.fullmatch(r"[0-9]{4}-[0-9]{2}-[0-9]{2}", target_date) is None
            ):
                return error("Choose a valid target date.")
            try:
                parsed_date = datetime.strptime(target_date, "%Y-%m-%d").date()
                if parsed_date < datetime.now(timezone.utc).date():
                    return error("Target date must be today or later.")
            except ValueError:
                return error("Choose a valid target date.")

    goal = {
            "id": "GOAL-" + secrets.token_hex(7).upper(),
            "name": name.strip(),
            "target_amount": str(target),
            "saved_amount": "0.00",
            "target_date": target_date or None,
            "created_at": datetime.now(timezone.utc).isoformat(),
    }
    goals = account.setdefault("savings_goals", [])
    goals.insert(0, goal)
    if not bank.save_data():
            goals.remove(goal)
            return error("Could not save this savings goal.", 503)
    return jsonify({"success": True, "goal": goal}), 201


@app.post("/api/savings-goals/<goal_id>/contribute")
def contribute_to_savings_goal(goal_id):
    return _change_savings_goal_balance(goal_id, request_json(), "contribute")


@app.post("/api/savings-goals/<goal_id>/withdraw")
def withdraw_from_savings_goal(goal_id):
    return _change_savings_goal_balance(goal_id, request_json(), "withdraw")


def _change_savings_goal_balance(goal_id, data, action):
    account = authenticated_account()
    if account is None:
            return error("Please login first.", 401)
    if data is None:
            return error("A JSON request body is required.")
    amount = bank.parse_amount(data.get("amount"))
    if amount is None or amount > MAX_TRANSACTION_AMOUNT:
            return error("Enter a valid amount not exceeding 500 crore.")
    goal = next(
            (
                item
                for item in account.get("savings_goals", [])
                if item.get("id") == goal_id
            ),
            None,
    )
    if goal is None:
            return error("Savings goal not found.", 404)
    try:
            saved = Decimal(str(goal.get("saved_amount", "0")))
            target = Decimal(str(goal.get("target_amount")))
    except (InvalidOperation, TypeError, ValueError):
            return error("Savings goal data is invalid.", 409)
    if (
            not saved.is_finite()
            or saved < 0
            or not target.is_finite()
            or target <= 0
    ):
            return error("Savings goal data is invalid.", 409)
    if action == "contribute":
            if amount > bank.available_balance(account):
                return error("Contribution exceeds your available balance.")
            new_saved = saved + amount
            if new_saved > target:
                return error("Contribution exceeds the remaining amount for this goal.")
            transaction_type = "SAVINGS_CONTRIBUTION"
    else:
            if amount > saved:
                return error("Withdrawal exceeds the amount allocated to this goal.")
            new_saved = saved - amount
            transaction_type = "SAVINGS_WITHDRAWAL"

    goal["saved_amount"] = str(new_saved)
    transaction = append_transaction(
            account,
            transaction_type,
            amount,
            goal_id=goal_id,
            description=f"{action.title()} to savings goal: {goal['name']}",
    )
    if not bank.save_data():
            goal["saved_amount"] = str(saved)
            account["transactions"].remove(transaction)
            return error("Could not update this savings goal.", 503)
    return jsonify({
            "success": True,
            "goal": goal,
            "available_balance": str(bank.available_balance(account)),
    })


@app.post("/api/transactions/<transaction_id>/dispute")
def submit_transaction_dispute(transaction_id):
    account = authenticated_account()
    if account is None:
            return error("Please login first.", 401)
    data = request_json()
    if data is None:
            return error("A JSON request body is required.")

    issue = data.get("issue")
    notes = data.get("notes", "")
    if not isinstance(issue, str) or issue not in {
            "UNRECOGNIZED",
            "DUPLICATE",
            "INCORRECT_AMOUNT",
            "OTHER",
    }:
            return error("Choose a supported dispute reason.")
    if not isinstance(notes, str):
            return error("Dispute notes must be text.")
    notes = notes.strip()
    if len(notes) > 500:
            return error("Dispute notes cannot exceed 500 characters.")

    transaction = next(
            (
                item
                for item in account.get("transactions", [])
                if item.get("id") == transaction_id
            ),
            None,
    )
    if transaction is None:
            return error("Transaction not found.", 404)
    if transaction.get("status", "COMPLETED") != "COMPLETED":
            return error("Only completed transactions can be disputed.", 409)
    if bank.disputes_collection.find_one({
            "account_number": account["account_number"],
            "transaction_id": transaction_id,
            "status": {"$in": ["OPEN", "UNDER_REVIEW"]},
    }):
            return error("An active dispute already exists for this transaction.", 409)

    now = datetime.now(timezone.utc).isoformat()
    dispute = {
            "id": "DSP-" + secrets.token_hex(8).upper(),
            "account_number": account["account_number"],
            "transaction_id": transaction_id,
            "transaction_type": transaction.get("type"),
            "amount": str(transaction.get("amount", "0")),
            "issue": issue,
            "notes": notes,
            "status": "OPEN",
            "reversed": False,
            "created_at": now,
            "updated_at": now,
            "history": [{"status": "OPEN", "at": now, "actor": "customer"}],
    }
    previous_dispute_id = transaction.get("dispute_id")
    transaction["dispute_id"] = dispute["id"]
    create_notification(
            account,
            "INFO",
            "Dispute submitted",
            f"Your dispute for transaction {transaction_id} was submitted for review.",
    )
    try:
            with bank.mongo_client.start_session() as mongo_session:
                with mongo_session.start_transaction():
                    bank.save_accounts_atomic(
                        [account["account_number"]],
                        session=mongo_session,
                    )
                    bank.disputes_collection.insert_one(
                        copy.deepcopy(dispute),
                        session=mongo_session,
                    )
                    bank.audit_log_collection.insert_one(
                        {
                            "id": "AUD-" + secrets.token_hex(8).upper(),
                            "actor": account["account_number"],
                            "action": "DISPUTE_SUBMITTED",
                            "entity_id": dispute["id"],
                            "created_at": now,
                        },
                        session=mongo_session,
                    )
            bank.mark_accounts_persisted([account["account_number"]])
    except Exception:
            if previous_dispute_id is None:
                transaction.pop("dispute_id", None)
            else:
                transaction["dispute_id"] = previous_dispute_id
            account["notifications"].pop(0)
            logger.exception("Could not save transaction dispute")
            return error("Could not submit this dispute. Please try again.", 503)

    return jsonify({"success": True, "dispute": dispute}), 201


@app.get("/api/disputes")
def get_customer_disputes():
    account = authenticated_account()
    if account is None:
            return error("Please login first.", 401)
    disputes = list(bank.disputes_collection.find(
            {"account_number": account["account_number"]},
            {"_id": 0},
    ).sort("created_at", -1))
    return jsonify({"success": True, "disputes": disputes})


@app.get("/api/staff/disputes")
def staff_disputes():
    if not require_staff():
            return error("Staff authorization is required.", 403)
    status = request.args.get("status")
    query = {}
    if status:
            if status not in {"OPEN", "UNDER_REVIEW", "RESOLVED", "DECLINED"}:
                return error("Unsupported dispute status.")
            query["status"] = status
    disputes = list(
            bank.disputes_collection.find(query, {"_id": 0}).sort("created_at", -1)
    )
    for dispute in disputes:
        account_number = str(dispute.pop("account_number", ""))
        dispute["account_number_masked"] = "•••• " + account_number[-4:]
    return jsonify({"success": True, "disputes": disputes})


def _append_audit_entry(mongo_session, action, entity_id, details=None):
    bank.audit_log_collection.insert_one(
            {
                "id": "AUD-" + secrets.token_hex(8).upper(),
                "actor": session.get("staff_username", "staff"),
                "action": action,
                "entity_id": entity_id,
                "details": details or {},
                "created_at": datetime.now(timezone.utc).isoformat(),
            },
            session=mongo_session,
    )


@app.get("/api/staff/me")
def staff_identity():
    if not require_staff():
        return error("Staff authorization is required.", 403)
    return jsonify({
        "success": True,
        "staff": {
            "username": session.get("staff_username"),
            "role": session.get("staff_role"),
        },
    })


def public_staff_account(staff_user, source):
    return {
        "id": staff_user.get("id"),
        "username": staff_user["username"],
        "role": staff_user["role"],
        "active": staff_user.get("active", True),
        "source": source,
        "source_configured": staff_user.get("source_configured", True),
        "created_by": staff_user.get("created_by"),
        "created_at": staff_user.get("created_at"),
        "revoked_by": staff_user.get("revoked_by"),
        "revoked_at": staff_user.get("revoked_at"),
    }


def staff_directory_records():
    environment_users = configured_staff_users()
    stored_users = list(
        staff_users_collection.find(
            {},
            {"_id": 0, "password_hash": 0},
        )
    )
    stored_by_key = {
        user.get("username_key"): user
        for user in stored_users
        if user.get("username_key")
    }

    users = []
    for username_key, configured_user in environment_users.items():
        override = stored_by_key.get(username_key)
        if override is not None and override.get("source") == "environment":
            user = dict(override)
            user["active"] = override.get("active", True)
            user["revoked_by"] = override.get("revoked_by")
            user["revoked_at"] = override.get("revoked_at")
            user["created_by"] = override.get("created_by")
            user["created_at"] = override.get("created_at")
        else:
            user = {}
        users.append({
            **user,
            "id": user.get("id", f"ENV-{username_key}"),
            "username": configured_user["username"],
            "role": configured_user["role"],
            "active": user.get("active", True),
            "source": "environment",
            "source_configured": True,
        })

    for stored_user in stored_users:
        if stored_user.get("source") == "environment":
            if stored_user.get("username_key") in environment_users:
                continue
            users.append({
                **stored_user,
                "active": False,
                "source": "environment",
                "source_configured": False,
            })
        else:
            users.append({
                **stored_user,
                "active": stored_user.get("active", True),
                "source": "managed",
                "source_configured": True,
            })
    return users


def _update_staff_account(staff_user, updates, action, audit_details):
    now = datetime.now(timezone.utc).isoformat()
    username_key = staff_user["username"].strip().casefold()
    updates = {**updates, "updated_at": now}
    try:
        with bank.mongo_client.start_session() as mongo_session:
            with mongo_session.start_transaction():
                if staff_user["source"] == "environment":
                    update = {
                        "$setOnInsert": {
                            "id": staff_user["id"],
                            "username": staff_user["username"],
                            "username_key": username_key,
                            "source": "environment",
                            "created_by": "server configuration",
                            "created_at": now,
                        },
                        "$set": updates,
                    }
                    result = staff_users_collection.update_one(
                        {
                            "username_key": username_key,
                            "source": "environment",
                        },
                        update,
                        upsert=True,
                        session=mongo_session,
                    )
                else:
                    result = staff_users_collection.update_one(
                        {"id": staff_user["id"], "source": {"$ne": "environment"}},
                        {"$set": updates},
                        session=mongo_session,
                    )
                    if result.matched_count != 1:
                        raise LookupError("Staff account no longer exists")

                if (
                    action == "STAFF_ACCESS_REVOKED"
                    and staff_user["role"] == "admin"
                ):
                    staff_access_guard_collection.update_one(
                        {"_id": "admin-access"},
                        {"$inc": {"revision": 1}},
                        upsert=True,
                        session=mongo_session,
                    )

                if action == "STAFF_ACCESS_REVOKED":
                    bank.sessions_collection.update_many(
                        {
                            "role": "staff",
                            "staff_username_key": username_key,
                            "revoked": {"$ne": True},
                        },
                        {
                            "$set": {
                                "revoked": True,
                                "revoked_at": now,
                            }
                        },
                        session=mongo_session,
                    )
                elif action == "STAFF_PASSWORD_RESET":
                    bank.sessions_collection.update_many(
                        {
                            "role": "staff",
                            "staff_username_key": username_key,
                            "revoked": {"$ne": True},
                        },
                        {
                            "$set": {
                                "revoked": True,
                                "revoked_at": now,
                            }
                        },
                        session=mongo_session,
                    )

                _append_audit_entry(
                    mongo_session,
                    action,
                    staff_user["id"],
                    audit_details,
                )
    except Exception:
        logger.exception("Could not update staff account %s", staff_user["id"])
        return False
    return True


def _staff_account_by_id(staff_id):
    for user in staff_directory_records():
        if user.get("id") == staff_id:
            return user
    return None


@app.get("/api/staff/users")
def staff_users_list():
    if not require_staff("staff:manage"):
        return error("Staff authorization is required.", 403)

    try:
        users = [
            public_staff_account(user, user["source"])
            for user in staff_directory_records()
        ]
    except ValueError:
        logger.exception("Staff user configuration is invalid")
        return error("Staff access configuration is invalid.", 503)
    except Exception:
        logger.exception("Could not load staff accounts")
        return error("Could not load staff accounts.", 503)

    users.sort(key=lambda user: user["username"].casefold())
    if not _record_staff_access("STAFF_USERS_VIEWED", len(users)):
        return error("Could not record staff account access.", 503)
    return jsonify({"success": True, "staff_users": users})


@app.post("/api/staff/users")
def staff_user_create():
    if not require_staff("staff:manage"):
        return error("Staff authorization is required.", 403)
    data = request_json()
    if data is None:
        return error("A JSON request body is required.")

    username = data.get("username")
    password = data.get("password")
    role = data.get("role")
    if (
        not isinstance(username, str)
        or not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9._-]{2,31}", username.strip())
    ):
        return error(
            "Username must be 3-32 characters and use letters, numbers, '.', '_' or '-'."
        )
    if (
        not isinstance(password, str)
        or len(password) < 12
        or len(password) > 128
        or not password.strip()
    ):
        return error("Password must contain between 12 and 128 characters.")
    if not isinstance(role, str) or role not in STAFF_ROLES:
        return error("Choose a supported staff role.")

    username = username.strip()
    username_key = username.casefold()
    try:
        if username_key in configured_staff_users():
            return error("A staff account with this username already exists.", 409)
    except ValueError:
        logger.exception("Staff user configuration is invalid")
        return error("Staff access configuration is invalid.", 503)

    now = datetime.now(timezone.utc).isoformat()
    staff_user = {
        "id": "STF-" + secrets.token_hex(8).upper(),
        "username": username,
        "username_key": username_key,
        "password_hash": generate_password_hash(password),
        "role": role,
        "active": True,
        "source": "managed",
        "created_by": session.get("staff_username", "staff"),
        "created_at": now,
    }
    try:
        with bank.mongo_client.start_session() as mongo_session:
            with mongo_session.start_transaction():
                staff_users_collection.insert_one(
                    staff_user,
                    session=mongo_session,
                )
                _append_audit_entry(
                    mongo_session,
                    "STAFF_ACCOUNT_CREATED",
                    staff_user["id"],
                    {"username": username, "role": role},
                )
    except DuplicateKeyError:
        return error("A staff account with this username already exists.", 409)
    except Exception:
        logger.exception("Could not create staff account")
        return error("Could not create the staff account.", 503)

    return jsonify({
        "success": True,
        "message": "Staff account created.",
        "staff_user": public_staff_account(staff_user, "managed"),
    }), 201


@app.post("/api/staff/users/<staff_id>/password")
def staff_user_password_reset(staff_id):
    if not require_staff("staff:manage"):
        return error("Staff authorization is required.", 403)
    data = request_json()
    if data is None:
        return error("A JSON request body is required.")
    password = data.get("password")
    if (
        not isinstance(password, str)
        or len(password) < 12
        or len(password) > 128
        or not password.strip()
    ):
        return error("Password must contain between 12 and 128 characters.")

    try:
        staff_user = _staff_account_by_id(staff_id)
    except ValueError:
        logger.exception("Staff user configuration is invalid")
        return error("Staff access configuration is invalid.", 503)
    except Exception:
        logger.exception("Could not load staff account for password reset")
        return error("Could not load the staff account.", 503)
    if staff_user is None:
        return error("Staff account not found.", 404)
    if not staff_user.get("active"):
        return error("Reactivate this account before resetting its password.", 409)
    if staff_user["source"] == "environment" and not staff_user.get("source_configured"):
        return error("This account is no longer configured on the server.", 409)

    now = datetime.now(timezone.utc).isoformat()
    password_hash = generate_password_hash(password)
    updates = {
        "password_hash": password_hash,
        "password_changed_at": now,
    }
    if staff_user["source"] == "environment":
        updates["role"] = staff_user["role"]
    if not _update_staff_account(
        staff_user,
        updates,
        "STAFF_PASSWORD_RESET",
        {"username": staff_user["username"], "role": staff_user["role"]},
    ):
        return error("Could not reset the staff password.", 503)

    return jsonify({
        "success": True,
        "message": "Password reset. The user must sign in again.",
    })


@app.post("/api/staff/users/<staff_id>/revoke")
def staff_user_revoke(staff_id):
    if not require_staff("staff:manage"):
        return error("Staff authorization is required.", 403)
    try:
        staff_user = _staff_account_by_id(staff_id)
        directory = staff_directory_records()
    except ValueError:
        logger.exception("Staff user configuration is invalid")
        return error("Staff access configuration is invalid.", 503)
    except Exception:
        logger.exception("Could not load staff accounts for revocation")
        return error("Could not load staff accounts.", 503)
    if staff_user is None:
        return error("Staff account not found.", 404)
    if not staff_user.get("active"):
        return error("Staff account is already inactive.", 409)
    username_key = staff_user["username"].strip().casefold()
    if username_key == str(session.get("staff_username", "")).strip().casefold():
        return error("You cannot revoke your own staff access.", 409)
    if staff_user["role"] == "admin" and not any(
        user.get("active")
        and user.get("role") == "admin"
        and user["username"].strip().casefold() != username_key
        for user in directory
    ):
        return error("The last active admin account cannot be revoked.", 409)

    now = datetime.now(timezone.utc).isoformat()
    updates = {
        "active": False,
        "revoked_by": session.get("staff_username", "staff"),
        "revoked_at": now,
        "access_revoked_at": now,
    }
    if staff_user["source"] == "environment":
        updates["role"] = staff_user["role"]
    if not _update_staff_account(
        staff_user,
        updates,
        "STAFF_ACCESS_REVOKED",
        {"username": staff_user["username"], "role": staff_user["role"]},
    ):
        return error("Could not revoke staff access.", 503)
    return jsonify({"success": True, "message": "Staff access revoked."})


@app.post("/api/staff/users/<staff_id>/reactivate")
def staff_user_reactivate(staff_id):
    if not require_staff("staff:manage"):
        return error("Staff authorization is required.", 403)
    try:
        staff_user = _staff_account_by_id(staff_id)
    except ValueError:
        logger.exception("Staff user configuration is invalid")
        return error("Staff access configuration is invalid.", 503)
    except Exception:
        logger.exception("Could not load staff account for reactivation")
        return error("Could not load the staff account.", 503)
    if staff_user is None:
        return error("Staff account not found.", 404)
    if staff_user.get("active"):
        return error("Staff account is already active.", 409)
    if staff_user["source"] == "environment" and not staff_user.get("source_configured"):
        return error("This account is no longer configured on the server.", 409)

    updates = {
        "active": True,
        "revoked_by": None,
        "revoked_at": None,
    }
    if staff_user["source"] == "environment":
        updates["role"] = staff_user["role"]
    if not _update_staff_account(
        staff_user,
        updates,
        "STAFF_ACCESS_REACTIVATED",
        {"username": staff_user["username"], "role": staff_user["role"]},
    ):
        return error("Could not reactivate staff access.", 503)
    return jsonify({"success": True, "message": "Staff access reactivated."})


@app.get("/api/staff/dashboard")
def staff_dashboard():
    if not require_staff():
        return error("Staff authorization is required.", 403)

    active_disputes = list(bank.disputes_collection.find(
        {"status": {"$in": ["OPEN", "UNDER_REVIEW"]}},
        {"_id": 0, "id": 1, "status": 1, "created_at": 1},
    ))
    all_flags = list(staff_account_flags.find(
        {},
        {
            "_id": 0,
            "id": 1,
            "account_number": 1,
            "reason": 1,
            "status": 1,
            "created_at": 1,
        },
    ))
    active_flags = [
        flag for flag in all_flags if flag.get("status") == "ACTIVE"
    ]
    now = datetime.now(timezone.utc)
    dispute_ages = [
        (now - created_at).total_seconds() / 3600
        for created_at in (
            _iso_datetime(item.get("created_at")) for item in active_disputes
        )
        if created_at is not None
    ]
    recent_flags = sorted(
        all_flags,
        key=lambda item: item.get("created_at", ""),
        reverse=True,
    )[:5]
    return jsonify({
        "success": True,
        "summary": {
            "open_disputes": sum(
                item.get("status") == "OPEN" for item in active_disputes
            ),
            "under_review_disputes": sum(
                item.get("status") == "UNDER_REVIEW" for item in active_disputes
            ),
            "oldest_dispute_hours": round(max(dispute_ages), 1) if dispute_ages else 0,
            "active_account_flags": len(active_flags),
            "pending_staff_work": len(active_disputes) + len(active_flags),
        },
        "recent_flags": [
            {
                "id": flag.get("id"),
                "account_ref": _staff_account_ref(flag.get("account_number", "")),
                "account_number_masked": (
                    "•••• " + str(flag.get("account_number", ""))[-4:]
                ),
                "reason": flag.get("reason", ""),
                "status": flag.get("status", "ACTIVE"),
                "created_at": flag.get("created_at"),
            }
            for flag in recent_flags
        ],
    })


@app.get("/api/staff/customers")
def staff_customer_search():
    if not require_staff():
        return error("Staff authorization is required.", 403)
    pagination = staff_page_params()
    if pagination is None:
        return error("page must be positive and page_size must be between 1 and 100.")
    page, page_size = pagination
    search = request.args.get("q", "").strip()
    if len(search) > 100:
        return error("Search text cannot exceed 100 characters.")

    records = list(bank.accounts_collection.find(
        {},
        {
            "_id": 0,
            "account_number": 1,
            "name": 1,
            "email": 1,
            "locked_until": 1,
            "transactions": 1,
        },
    ))
    if search:
        needle = search.casefold()
        records = [
            record for record in records
            if needle in str(record.get("account_number", "")).casefold()
            or needle in str(record.get("name", "")).casefold()
            or needle in str(record.get("email", "")).casefold()
        ]
    records.sort(key=lambda item: str(item.get("name", "")).casefold())
    total = len(records)
    start = (page - 1) * page_size
    page_records = records[start:start + page_size]
    flag_counts = {}
    for flag in staff_account_flags.find(
        {"status": "ACTIVE"},
        {"_id": 0, "account_number": 1},
    ):
        account_number = flag.get("account_number")
        flag_counts[account_number] = flag_counts.get(account_number, 0) + 1

    now = time.time()
    customers = []
    for record in page_records:
        account_number = str(record.get("account_number", ""))
        transactions = sorted(
            record.get("transactions", []),
            key=lambda item: item.get("created_at", ""),
            reverse=True,
        )[:3]
        customers.append({
            "account_ref": _staff_account_ref(account_number),
            "account_number_masked": "•••• " + account_number[-4:],
            "name": record.get("name", ""),
            "email_masked": _mask_email(record.get("email", "")),
            "status": (
                "PIN_LOCKED_TEMPORARILY"
                if float(record.get("locked_until", 0) or 0) > now
                else "ACTIVE"
            ),
            "active_flag_count": flag_counts.get(account_number, 0),
            "recent_transactions": [
                {
                    "id": transaction.get("id"),
                    "type": transaction.get("type"),
                    "amount": str(transaction.get("amount", "0")),
                    "status": transaction.get("status"),
                    "created_at": transaction.get("created_at"),
                }
                for transaction in transactions
            ],
        })

    if not _record_staff_access("CUSTOMER_SEARCH", len(customers)):
        return error("Could not record customer lookup access.", 503)
    return jsonify({
        "success": True,
        "customers": customers,
        "pagination": {
            "page": page,
            "page_size": page_size,
            "total": total,
            "pages": (total + page_size - 1) // page_size,
        },
    })


@app.get("/api/staff/transactions")
def staff_transaction_search():
    if not require_staff():
        return error("Staff authorization is required.", 403)
    pagination = staff_page_params()
    if pagination is None:
        return error("page must be positive and page_size must be between 1 and 100.")
    page, page_size = pagination
    search = request.args.get("q", "").strip().casefold()
    account_search = request.args.get("account_number", "").strip()
    transaction_type = request.args.get("type", "").strip().upper()
    status = request.args.get("status", "").strip().upper()
    raw_from = request.args.get("from", "")
    raw_to = request.args.get("to", "")
    from_date = _iso_datetime(raw_from)
    to_date = _iso_datetime(raw_to)
    if raw_to and len(raw_to) == 10 and to_date is not None:
        to_date += timedelta(days=1) - timedelta(microseconds=1)
    if raw_from and from_date is None:
        return error("The from date must be a valid ISO date or timestamp.")
    if raw_to and to_date is None:
        return error("The to date must be a valid ISO date or timestamp.")
    try:
        minimum = Decimal(request.args["min_amount"]) if request.args.get("min_amount") else None
        maximum = Decimal(request.args["max_amount"]) if request.args.get("max_amount") else None
    except InvalidOperation:
        return error("Amount filters must be valid numbers.")
    if (
        (minimum is not None and (not minimum.is_finite() or minimum < 0))
        or (maximum is not None and (not maximum.is_finite() or maximum < 0))
        or (minimum is not None and maximum is not None and minimum > maximum)
    ):
        return error("Amount filters must be non-negative and minimum cannot exceed maximum.")
    if len(search) > 100 or len(account_search) > 11:
        return error("Search filters exceed their supported length.")

    results = []
    for account in bank.accounts_collection.find(
        {},
        {
            "_id": 0,
            "account_number": 1,
            "transactions": 1,
        },
    ):
        account_number = str(account.get("account_number", ""))
        if account_search and not account_number.endswith(account_search):
            continue
        for transaction in account.get("transactions", []):
            created_at = _iso_datetime(transaction.get("created_at"))
            amount = bank.parse_amount(transaction.get("amount", "0"))
            if transaction_type and str(transaction.get("type") or "").upper() != transaction_type:
                continue
            if status and str(transaction.get("status", "COMPLETED")).upper() != status:
                continue
            if from_date and (created_at is None or created_at < from_date):
                continue
            if to_date and (created_at is None or created_at > to_date):
                continue
            if minimum is not None and (amount is None or amount < minimum):
                continue
            if maximum is not None and (amount is None or amount > maximum):
                continue
            searchable = " ".join(
                str(transaction.get(key, ""))
                for key in ("id", "reference", "description")
            ).casefold()
            if search and search not in searchable:
                continue
            results.append({
                "account_ref": _staff_account_ref(account_number),
                "account_number_masked": "•••• " + account_number[-4:],
                "id": transaction.get("id"),
                "type": transaction.get("type"),
                "amount": str(transaction.get("amount", "0")),
                "status": transaction.get("status", "COMPLETED"),
                "reference": transaction.get("reference"),
                "description": transaction.get("description", ""),
                "created_at": transaction.get("created_at"),
            })
    results.sort(key=lambda item: item.get("created_at", ""), reverse=True)
    total = len(results)
    start = (page - 1) * page_size
    page_results = results[start:start + page_size]
    if not _record_staff_access("TRANSACTION_SEARCH", len(page_results)):
        return error("Could not record transaction search access.", 503)
    return jsonify({
        "success": True,
        "transactions": page_results,
        "pagination": {
            "page": page,
            "page_size": page_size,
            "total": total,
            "pages": (total + page_size - 1) // page_size,
        },
    })


@app.get("/api/staff/accounts/<account_ref>/flags")
def staff_account_flags_list(account_ref):
    if not require_staff():
        return error("Staff authorization is required.", 403)
    account_number = _resolve_staff_account_ref(account_ref)
    if account_number is None:
        return error("Account not found.", 404)
    flags = list(staff_account_flags.find(
        {"account_number": account_number},
        {"_id": 0, "account_number": 0},
    ))
    flags.sort(key=lambda item: item.get("created_at", ""), reverse=True)
    if not _record_staff_access("ACCOUNT_FLAGS_VIEWED", len(flags)):
        return error("Could not record account flag access.", 503)
    return jsonify({"success": True, "flags": flags})


@app.post("/api/staff/accounts/<account_ref>/flags")
def staff_account_flag_create(account_ref):
    if not require_staff("flags:manage"):
        return error("Staff authorization is required.", 403)
    account_number = _resolve_staff_account_ref(account_ref)
    if account_number is None:
        return error("Account not found.", 404)
    data = request_json()
    if data is None:
        return error("A JSON request body is required.")
    reason = data.get("reason")
    if not isinstance(reason, str) or not reason.strip() or len(reason.strip()) > 500:
        return error("A flag reason between 1 and 500 characters is required.")
    if staff_account_flags.find_one({
        "account_number": account_number,
        "status": "ACTIVE",
    }):
        return error("This account already has an active support flag.", 409)

    now = datetime.now(timezone.utc).isoformat()
    flag = {
        "id": "FLG-" + secrets.token_hex(8).upper(),
        "account_number": account_number,
        "reason": reason.strip(),
        "status": "ACTIVE",
        "created_by": session.get("staff_username", "staff"),
        "created_at": now,
        "updated_at": now,
    }
    try:
        with bank.mongo_client.start_session() as mongo_session:
            with mongo_session.start_transaction():
                staff_account_flags.insert_one(flag, session=mongo_session)
                _append_audit_entry(
                    mongo_session,
                    "ACCOUNT_FLAG_CREATED",
                    flag["id"],
                    {"account_ref": account_ref, "reason": flag["reason"]},
                )
    except Exception:
        logger.exception("Could not create staff account flag")
        return error("Could not save the account flag.", 503)
    flag.pop("account_number")
    return jsonify({"success": True, "flag": flag}), 201


@app.patch("/api/staff/accounts/<account_ref>/flags/<flag_id>")
def staff_account_flag_clear(account_ref, flag_id):
    if not require_staff("flags:manage"):
        return error("Staff authorization is required.", 403)
    account_number = _resolve_staff_account_ref(account_ref)
    if account_number is None:
        return error("Account not found.", 404)
    data = request_json()
    if data is None:
        return error("A JSON request body is required.")
    resolution = data.get("resolution")
    if (
        not isinstance(resolution, str)
        or not resolution.strip()
        or len(resolution.strip()) > 500
    ):
        return error("A resolution between 1 and 500 characters is required.")
    now = datetime.now(timezone.utc).isoformat()
    try:
        with bank.mongo_client.start_session() as mongo_session:
            with mongo_session.start_transaction():
                result = staff_account_flags.update_one(
                    {
                        "id": flag_id,
                        "account_number": account_number,
                        "status": "ACTIVE",
                    },
                    {"$set": {
                        "status": "RESOLVED",
                        "resolution": resolution.strip(),
                        "resolved_by": session.get("staff_username", "staff"),
                        "updated_at": now,
                    }},
                    session=mongo_session,
                )
                if result.matched_count != 1:
                    return error("Active account flag not found.", 404)
                _append_audit_entry(
                    mongo_session,
                    "ACCOUNT_FLAG_RESOLVED",
                    flag_id,
                    {"account_ref": account_ref, "resolution": resolution.strip()},
                )
    except Exception:
        logger.exception("Could not resolve staff account flag")
        return error("Could not update the account flag.", 503)
    return jsonify({"success": True, "message": "Account flag resolved."})


@app.get("/api/staff/audit-log")
def staff_audit_log():
    if not require_staff("audit:read"):
        return error("Staff authorization is required.", 403)
    pagination = staff_page_params()
    if pagination is None:
        return error("page must be positive and page_size must be between 1 and 100.")
    page, page_size = pagination
    actor = request.args.get("actor", "").strip().casefold()
    action = request.args.get("action", "").strip().casefold()
    entity_id = request.args.get("entity_id", "").strip().casefold()
    raw_from = request.args.get("from", "")
    raw_to = request.args.get("to", "")
    from_date = _iso_datetime(raw_from)
    to_date = _iso_datetime(raw_to)
    if raw_to and len(raw_to) == 10 and to_date is not None:
        to_date += timedelta(days=1) - timedelta(microseconds=1)
    if raw_from and from_date is None:
        return error("The from date must be a valid ISO date or timestamp.")
    if raw_to and to_date is None:
        return error("The to date must be a valid ISO date or timestamp.")

    records = []
    for entry in bank.audit_log_collection.find({}, {"_id": 0}):
        created_at = _iso_datetime(entry.get("created_at"))
        if actor and actor not in str(entry.get("actor", "")).casefold():
            continue
        if action and action not in str(entry.get("action", "")).casefold():
            continue
        if entity_id and entity_id not in str(entry.get("entity_id", "")).casefold():
            continue
        if from_date and (created_at is None or created_at < from_date):
            continue
        if to_date and (created_at is None or created_at > to_date):
            continue
        records.append(entry)
    records.sort(key=lambda item: item.get("created_at", ""), reverse=True)
    total = len(records)
    start = (page - 1) * page_size
    public_entries = []
    for entry in records[start:start + page_size]:
        public_entry = dict(entry)
        actor = str(public_entry.get("actor", ""))
        if re.fullmatch(r"[0-9]{11}", actor):
            public_entry["actor"] = "Account •••• " + actor[-4:]
        public_entries.append(public_entry)
    return jsonify({
        "success": True,
        "entries": public_entries,
        "pagination": {
            "page": page,
            "page_size": page_size,
            "total": total,
            "pages": (total + page_size - 1) // page_size,
        },
    })


@app.patch("/api/staff/disputes/<dispute_id>")
def review_dispute(dispute_id):
    if not require_staff("disputes:review"):
        return error("Staff authorization is required.", 403)
    data = request_json()
    if data is None:
        return error("A JSON request body is required.")
    action = data.get("action")
    raw_resolution = data.get("resolution", "")
    if not isinstance(action, str) or action not in {
        "UNDER_REVIEW",
        "RESOLVED",
        "DECLINED",
    }:
        return error("Choose a supported dispute action.")
    if not isinstance(raw_resolution, str):
        return error("Resolution notes must be text.")
    resolution = raw_resolution.strip()
    reverse_transfer = data.get("reverse_transfer", False)
    if not isinstance(reverse_transfer, bool):
        return error("reverse_transfer must be true or false.")
    if len(resolution) > 500:
        return error("Resolution notes cannot exceed 500 characters.")
    if action in {"RESOLVED", "DECLINED"} and not resolution:
        return error("Add resolution notes before closing this dispute.")

    dispute = bank.disputes_collection.find_one(
        {"id": dispute_id},
        {"_id": 0},
    )
    if dispute is None:
        return error("Dispute not found.", 404)
    if action == "UNDER_REVIEW" and dispute["status"] != "OPEN":
        return error("Only open disputes can move to review.", 409)
    if action in {"RESOLVED", "DECLINED"} and dispute["status"] not in {
        "OPEN",
        "UNDER_REVIEW",
    }:
        return error("This dispute has already been resolved.", 409)
    if reverse_transfer and (
        action != "RESOLVED"
        or dispute.get("transaction_type") not in {"TRANSFER", "TRANSFER_RECEIVED"}
    ):
        return error("Only a transfer dispute can be resolved with a reversal.")

    now = datetime.now(timezone.utc).isoformat()
    updated = {
        "status": action,
        "updated_at": now,
        "resolution": resolution,
    }
    updated_history = list(dispute.get("history", []))
    updated_history.append({
        "status": action,
        "at": now,
        "actor": session.get("staff_username", "staff"),
        "notes": resolution,
    })
    updated["history"] = updated_history
    account_numbers = []
    sender = None
    recipient = None
    old_sender_balance = None
    old_recipient_balance = None
    old_sender_transactions = None
    old_recipient_transactions = None

    if reverse_transfer:
        disputed_account = bank.refresh_account(dispute["account_number"])
        if disputed_account is None:
            return error("Disputed account is unavailable.", 409)
        original = next(
            (
                item
                for item in disputed_account.get("transactions", [])
                if item.get("id") == dispute["transaction_id"]
            ),
            None,
        )
        if original is None or original.get("status") != "COMPLETED":
            return error("The transfer is no longer eligible for reversal.", 409)

        if original.get("type") == "TRANSFER":
            sender_number = disputed_account["account_number"]
            recipient_number = original.get("recipient_account")
        else:
            sender_number = original.get("sender_account")
            recipient_number = disputed_account["account_number"]
        sender = bank.refresh_account(sender_number) if sender_number else None
        recipient = bank.refresh_account(recipient_number) if recipient_number else None
        if sender is None or recipient is None:
            return error("Both transfer accounts must be available to reverse it.", 409)

        amount = Decimal(str(original["amount"]))
        if bank.available_balance(recipient) < amount:
            return error(
                "The recipient's available funds are insufficient for a safe reversal.",
                409,
            )

        sender_original = next(
            (
                item
                for item in sender.get("transactions", [])
                if item.get("id") == dispute["transaction_id"]
            ),
            None,
        )
        recipient_original = next(
            (
                item
                for item in recipient.get("transactions", [])
                if item.get("id") == dispute["transaction_id"]
            ),
            None,
        )
        if sender_original is None or recipient_original is None:
            return error("Transfer history is incomplete; reversal was not applied.", 409)

        old_sender_balance = sender["balance"]
        old_recipient_balance = recipient["balance"]
        old_sender_transactions = copy.deepcopy(sender.get("transactions", []))
        old_recipient_transactions = copy.deepcopy(recipient.get("transactions", []))
        reversal_id = "REV-" + secrets.token_hex(8).upper()
        sender["balance"] += amount
        recipient["balance"] -= amount
        for original_item in (sender_original, recipient_original):
            original_item["status"] = "REVERSED"
            original_item["reversed_by"] = reversal_id
        sender.setdefault("transactions", []).insert(0, {
            "id": reversal_id,
            "type": "TRANSFER_REVERSAL_CREDIT",
            "amount": str(amount),
            "status": "COMPLETED",
            "balance_after": str(sender["balance"]),
            "created_at": now,
            "reference": dispute["transaction_id"],
            "description": "Staff-approved transfer reversal",
        })
        recipient.setdefault("transactions", []).insert(0, {
            "id": reversal_id,
            "type": "TRANSFER_REVERSAL_DEBIT",
            "amount": str(amount),
            "status": "COMPLETED",
            "balance_after": str(recipient["balance"]),
            "created_at": now,
            "reference": dispute["transaction_id"],
            "description": "Staff-approved transfer reversal",
        })
        account_numbers = [sender_number, recipient_number]
        updated["reversed"] = True
        updated["reversal_id"] = reversal_id

    try:
        with bank.mongo_client.start_session() as mongo_session:
            with mongo_session.start_transaction():
                if account_numbers:
                    bank.save_accounts_atomic(
                        account_numbers,
                        session=mongo_session,
                    )
                result = bank.disputes_collection.update_one(
                    {
                        "id": dispute_id,
                        "status": dispute["status"],
                    },
                    {"$set": updated},
                    session=mongo_session,
                )
                if result.matched_count != 1:
                    raise bank.ConcurrentAccountWriteError(
                        "Dispute status changed in another review."
                    )
                _append_audit_entry(
                    mongo_session,
                    "DISPUTE_" + action,
                    dispute_id,
                    {
                        "reversed": reverse_transfer,
                        "resolution": resolution,
                    },
                )
        if account_numbers:
            bank.mark_accounts_persisted(account_numbers)
    except Exception:
        if sender is not None and recipient is not None:
            sender["balance"] = old_sender_balance
            recipient["balance"] = old_recipient_balance
            sender["transactions"] = old_sender_transactions
            recipient["transactions"] = old_recipient_transactions
        logger.exception("Could not commit staff dispute review")
        return error("Could not save the dispute review.", 503)

    public_dispute = {**dispute, **updated}
    account_number = str(public_dispute.pop("account_number", ""))
    public_dispute["account_number_masked"] = "•••• " + account_number[-4:]
    return jsonify({"success": True, "dispute": public_dispute})


if __name__ == "__main__":
    scheduled_worker = start_scheduled_transfer_worker()
    try:
        app.run(
            host="127.0.0.1",
            port=5000,
            debug=True
        )
    finally:
        if scheduled_worker is not None:
            scheduled_worker.terminate()
            scheduled_worker.wait()