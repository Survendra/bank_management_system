import os
import re
import time
import pyotp
import io
import base64
import qrcode
from datetime import datetime, timezone
import secrets
from decimal import Decimal
from flask import Flask, jsonify, request, session
from flask_cors import CORS

import bank_service as bank


app = Flask(__name__)

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

def error(message, status=400):
    return jsonify({
        "success": False,
        "message": message
    }), status


def request_json():
    data = request.get_json(silent=True)
    return data if isinstance(data, dict) else None


def authenticated_account():
    account_number = session.get("account_number")

    if not account_number:
        return None

    return bank.accounts.get(account_number)

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

@app.before_request
def enforce_session_timeout():
    if request.path in (
        "/api/login",
        "/api/register",
        "/api/health",
    ):
        return None

    if not session.get("account_number"):
        return None

    if session_timed_out():
        session.clear()

        return jsonify({
            "success": False,
            "message": "Your session has expired. Please login again.",
            "session_expired": True,
        }), 401

    session["last_activity"] = time.time()

    return None


@app.get("/api/health")
def health():
    return jsonify({
        "success": True,
        "message": "Bank API is running"
    })


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

    session.clear()
    session["account_number"] = account_number
    session.permanent = True
    session["login_time"] = time.time()
    session["last_activity"] = time.time()

    create_security_event(
        account,
        "Two-factor authentication login",
        "SUCCESS"
    )

    bank.save_data()

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

    account = bank.accounts.get(account_number)

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

    session.clear()
    session["account_number"] = account_number
    session.permanent = True
    session["login_time"] = time.time()
    session["last_activity"] = time.time()

    create_security_event(
        account,
        "Login",
        "SUCCESS"
    )

    bank.save_data()

    return jsonify({
        "success": True,
        "message": "Login successful.",
        "account": bank.public_account(account)
    })


@app.post("/api/logout")
def logout():
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

    if not bank.verify_pin(
        pin,
        account.get("pin_salt"),
        account.get("pin_hash"),
    ):
        create_notification(
            account,
            "error",
            "Card payment failed",
            "A card payment was declined because the security PIN was incorrect.",
        )

        bank.save_data()

        return error(
            "Incorrect security PIN.",
            401,
        )

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

    balance = Decimal(
        str(account["balance"])
    )

    if amount > balance:
        return error(
            "Insufficient account balance.",
            400,
        )

    now = datetime.now(timezone.utc)

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

    if not bank.save_data():
        account["balance"] += amount
        card["transactions"].remove(
            transaction
        )
        account["transactions"].remove(
            transaction
        )

        return error(
            "Payment failed. No changes were saved.",
            500,
        )

    create_notification(
        account,
        "success",
        "Card payment completed",
        (
            f"${amount:.2f} paid to "
            f"{merchant.strip()} using your card ending in "
            f"{card['last_four']}."
        ),
    )

    bank.save_data()

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
    amount
):
    transaction = {
        "id": (
            f"TXN-{int(time.time() * 1000)}-"
            f"{len(account['transactions']) + 1}"
        ),
        "type": transaction_type,
        "amount": str(amount),
        "balance_after": str(account["balance"]),
        "created_at": datetime.now(timezone.utc).isoformat(),
    }

    account["transactions"].insert(
        0,
        transaction
    )

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

    if amount > account["balance"]:
        return error("Insufficient funds.")

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

    if (
        not isinstance(current_pin, str)
        or not bank.verify_pin(
            current_pin,
            account["pin_salt"],
            account["pin_hash"]
        )
    ):
        return error(
            "Current PIN is incorrect.",
            401
        )

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

    account["pin_salt"], account["pin_hash"] = (
        bank.hash_pin(new_pin)
    )

    if not bank.save_data():
        account["pin_salt"] = old_salt
        account["pin_hash"] = old_hash

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

    beneficiary_id = str(
        data.get("beneficiary_id", "")
    ).strip()

    pin = data.get("pin")
    amount = bank.parse_amount(
        data.get("amount")
    )

    if amount is None or amount <= 0:
        return error(
            "Enter a valid transfer amount."
        )

    if (
        not isinstance(pin, str)
        or not bank.is_strong_pin(pin)
    ):
        return error(
            "Enter a valid 4-digit PIN."
        )

    current_time = time.time()

    if account.get("locked_until", 0) > current_time:
        return error(
            "Account temporarily locked. "
            "Please try again later.",
            423
        )

    if not bank.verify_pin(
        pin,
        account["pin_salt"],
        account["pin_hash"]
    ):
        account["failed_attempts"] = (
            account.get("failed_attempts", 0) + 1
        )

        if account["failed_attempts"] >= bank.MAX_PIN_ATTEMPTS:
            account["failed_attempts"] = 0
            account["locked_until"] = (
                current_time + bank.LOCK_DURATION
            )

        bank.save_data()

        return error(
            "Incorrect PIN.",
            401
        )

    account["failed_attempts"] = 0
    account["locked_until"] = 0

    beneficiary = find_beneficiary(
        account,
        beneficiary_id
    )

    if beneficiary is None:
        return error(
            "Beneficiary not found.",
            404
        )

    recipient = bank.accounts.get(
        beneficiary["account_number"]
    )

    if recipient is None:
        return error(
            "Beneficiary account no longer exists.",
            404
        )

    if account["balance"] < amount:
        return error(
            "Insufficient balance.",
            400
        )

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

    create_notification(
        account,
        "SUCCESS",
        "Transfer successful",
        (
            f"${amount:.2f} sent to "
            f"{recipient['name']}."
        )
    )

    create_notification(
        recipient,
        "SUCCESS",
        "Money received",
        (
            f"You received ${amount:.2f} "
            f"from {account['name']}."
        )
    )

    if not bank.save_data():
        account["balance"] = old_sender_balance
        recipient["balance"] = old_recipient_balance

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
            "Transfer failed. No money was transferred.",
            500
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

if __name__ == "__main__":
    app.run(
        host="127.0.0.1",
        port=5000,
        debug=True
    )