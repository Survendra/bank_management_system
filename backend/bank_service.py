import json
import math
import os
import re
import secrets
import tempfile
import time
import hmac
import hashlib
from decimal import Decimal, InvalidOperation
from datetime import datetime, timezone
from dotenv import load_dotenv
from pymongo import MongoClient

load_dotenv()

MONGO_URI = os.getenv("MONGO_URI")

if not MONGO_URI:
    raise RuntimeError("MONGO_URI is not configured.")

mongo_client = MongoClient(
    MONGO_URI,
    serverSelectionTimeoutMS=5000,
)

mongo_db = mongo_client["bluebank"]

accounts_collection = mongo_db["accounts"]
transactions_collection = mongo_db["transactions"]
beneficiaries_collection = mongo_db["beneficiaries"]
cards_collection = mongo_db["cards"]
security_events_collection = mongo_db["security_events"]
notifications_collection = mongo_db["notifications"]

accounts_collection.create_index(
    [("account_number", 1)],
    unique=True
)


MAX_PIN_ATTEMPTS = 3
LOCK_DURATION = 60
PIN_ITERATIONS = 600000

accounts = {}
storage_ready = False


def is_valid_name(name):
    return isinstance(name, str) and bool(
        re.fullmatch(r"[A-Za-z]+(?:[ .'-][A-Za-z]+)*", name.strip())
    )


def is_strong_pin(pin):
    if not isinstance(pin, str) or not re.fullmatch(r"[0-9]{4}", pin):
        return False

    weak = {
        "0123", "1234", "2345", "3456", "4567", "5678", "6789",
        "9876", "8765", "7654", "6543", "5432", "4321", "3210",
        "0000", "1111", "2222", "3333", "4444", "5555", "6666",
        "7777", "8888", "9999", "1212", "1122", "1004", "2000",
        "2020", "2580",
    }

    return pin not in weak and len(set(pin)) > 1


def hash_pin(pin, salt=None):
    if salt is None:
        salt = secrets.token_bytes(16).hex()

    digest = hashlib.pbkdf2_hmac(
        "sha256",
        pin.encode("utf-8"),
        bytes.fromhex(salt),
        PIN_ITERATIONS,
    ).hex()

    return salt, digest


def verify_pin(pin, salt, stored_hash):
    try:
        _, entered_hash = hash_pin(pin, salt)
        return hmac.compare_digest(entered_hash, stored_hash)
    except (TypeError, ValueError):
        return False


def parse_amount(raw):
    if not isinstance(raw, (str, int, float, Decimal)) or isinstance(raw, bool):
        return None

    value_text = str(raw).strip()

    if not re.fullmatch(r"[0-9]+(?:\.[0-9]{1,2})?", value_text):
        return None

    try:
        amount = Decimal(value_text)

        if amount.is_finite() and amount > 0:
            return amount

    except InvalidOperation:
        pass

    return None


def save_data():
    global storage_ready

    try:
        for account_number, account in accounts.items():
            document = dict(account)

            # MongoDB should store the account number as a field
            document["account_number"] = account_number

            # Remove any MongoDB-generated ID if present
            document.pop("_id", None)

            # Store Decimal balance safely as a string
            if isinstance(document.get("balance"), Decimal):
                document["balance"] = str(document["balance"])

            accounts_collection.update_one(
                {"account_number": account_number},
                {"$set": document},
                upsert=True,
            )

        storage_ready = True

        print(
            f"Saved {len(accounts)} accounts to MongoDB."
        )

        return True

    except Exception as exc:
        storage_ready = False

        print(
            f"MongoDB save error: "
            f"{type(exc).__name__}: {exc}"
        )
        raise


def load_data():
    global accounts, storage_ready

    accounts = {}

    try:
        valid = {}

        for item in accounts_collection.find({}):
            account_number = str(
                item.get("account_number", "")
            ).strip()

            if not re.fullmatch(
                r"[0-9]{11}",
                account_number,
            ):
                print(
                    f"REJECTED {account_number}: invalid account number"
                )
                continue

            if not isinstance(item, dict):
                continue

            record = dict(item)
            record.pop("_id", None)

            record["account_number"] = account_number

            try:
                record["balance"] = Decimal(
                    str(record.get("balance", "0"))
                )

                if not record["balance"].is_finite():
                    continue

                if record["balance"] < 0:
                    continue

                record["age"] = int(record.get("age", 0))

                if not 18 <= record["age"] <= 120:
                    continue

                record["name"] = str(
                    record.get("name", "")
                ).strip()

                record["email"] = str(
                    record.get("email", "")
                ).strip()

                if not is_valid_name(record["name"]):
                    continue

                record["failed_attempts"] = int(
                    record.get("failed_attempts", 0)
                )

                record["locked_until"] = float(
                    record.get("locked_until", 0)
                )

                if record["failed_attempts"] < 0:
                    record["failed_attempts"] = 0

                if record["failed_attempts"] > MAX_PIN_ATTEMPTS:
                    record["failed_attempts"] = MAX_PIN_ATTEMPTS

                if record["locked_until"] < 0:
                    record["locked_until"] = 0

                for field in [
                    "transactions",
                    "beneficiaries",
                    "notifications",
                    "security_activity",
                    "cards",
                    "virtual_cards",
                ]:
                    if not isinstance(record.get(field), list):
                        record[field] = []

                if not isinstance(
                    record.get("two_factor"),
                    dict,
                ):
                    record["two_factor"] = {
                        "enabled": False,
                        "secret": None,
                    }

                if not isinstance(
                    record["two_factor"].get("enabled"),
                    bool,
                ):
                    record["two_factor"]["enabled"] = False

                if (
                    record["two_factor"].get("secret")
                    is not None
                    and not isinstance(
                        record["two_factor"].get("secret"),
                        str,
                    )
                ):
                    record["two_factor"]["secret"] = None

                salt = record.get("pin_salt")
                pin_hash = record.get("pin_hash")

                if (salt is None) != (pin_hash is None):
                    print(
                        f"PIN FIELD MISMATCH: {account_number}"
                    )
                    continue

                if salt is not None:
                    if not re.fullmatch(
                        r"[0-9a-f]{32}",
                        str(salt),
                    ):
                        print(
                            f"INVALID PIN SALT: {account_number}"
                        )
                        continue

                    if not re.fullmatch(
                        r"[0-9a-f]{64}",
                        str(pin_hash),
                    ):
                        print(
                            f"INVALID PIN HASH: {account_number}"
                        )
                        continue

                valid[account_number] = record

            except (
                TypeError,
                ValueError,
                InvalidOperation,
            ) as exc:
                print(
                    f"ACCOUNT REJECTED: {account_number} | "
                    f"{type(exc).__name__}: {exc}"
                )
                continue

        accounts = valid
        storage_ready = True

        print(
            "Loaded accounts from MongoDB:",
            list(accounts.keys()),
        )

    except Exception as exc:
        print(
            f"MongoDB load error: "
            f"{type(exc).__name__}: {exc}"
        )
        accounts = {}
        storage_ready = False


def generate_account_number():
    while True:

        number = str(
            secrets.randbelow(90000000000)
            + 10000000000
        )

        if number not in accounts:
            return number


def public_account(account):
    return {
        "name": account["name"],
        "age": account["age"],
        "email": account.get("email", ""),
        "account_number": account["account_number"],
        "balance": str(account["balance"]),
    }

def generate_card_id():
    return "CARD-" + secrets.token_hex(6).upper()

def generate_virtual_card_id():
    return "VCARD-" + secrets.token_hex(6).upper()

def generate_card_number():
    while True:
        number = (
            "4"
            + "".join(
                str(secrets.randbelow(10))
                for _ in range(15)
            )
        )

        # Make sure this card number is not already in use.
        exists = any(
            any(
                card.get("card_number") == number
                for card in account.get("cards", [])
            )
            for account in accounts.values()
        )

        if not exists:
            return number

def generate_virtual_card_number():
    while True:
        number = (
            "4"
            + "".join(
                str(secrets.randbelow(10))
                for _ in range(15)
            )
        )

        physical_exists = any(
            any(
                card.get("card_number") == number
                for card in account.get("cards", [])
            )
            for account in accounts.values()
        )

        virtual_exists = any(
            any(
                card.get("card_number") == number
                for card in account.get("virtual_cards", [])
            )
            for account in accounts.values()
        )

        if not physical_exists and not virtual_exists:
            return number

def is_card_expired(card):
    now = datetime.now(timezone.utc)

    expiry_year = int(card.get("expiry_year", 0))
    expiry_month = int(card.get("expiry_month", 0))

    return (
        expiry_year < now.year
        or (
            expiry_year == now.year
            and expiry_month < now.month
        )
    )


def refresh_card_status(card):
    if card.get("status") in {
        "BLOCKED",
        "REPLACED",
    }:
        return False

    if is_card_expired(card):
        if card.get("status") != "EXPIRED":
            card["status"] = "EXPIRED"
            return True

    return False

def create_card(account, status="ISSUED"):
    now = datetime.now(timezone.utc)

    card_number = generate_card_number()

    card = {
        "id": generate_card_id(),
        "card_type": "DEBIT",
        "card_number": card_number,
        "last_four": card_number[-4:],
        "expiry_month": now.month,
        "expiry_year": now.year + 5,
        "status": status,
        "daily_limit": "2000.00",
        "issued_at": now.isoformat(),
        "transactions": [],
    }

    account.setdefault("cards", []).append(card)

    return card

def create_virtual_card(account):
    now = datetime.now(timezone.utc)

    card_number = generate_virtual_card_number()

    card = {
        "id": generate_virtual_card_id(),
        "card_type": "VIRTUAL",
        "card_number": card_number,
        "last_four": card_number[-4:],
        "expiry_month": now.month,
        "expiry_year": now.year + 3,
        "status": "ACTIVE",
        "daily_limit": "1000.00",
        "issued_at": now.isoformat(),
        "transactions": [],
    }

    account.setdefault(
        "virtual_cards",
        []
    ).append(card)

    return card

def public_card(card):
    return {
        "id": card["id"],
        "card_type": card["card_type"],
        "masked_number": (
            "•••• •••• •••• "
            + card["last_four"]
        ),
        "last_four": card["last_four"],
        "expiry": (
            f'{card["expiry_month"]:02d}/'
            f'{str(card["expiry_year"])[-2:]}'
        ),
        "status": card["status"],
        "daily_limit": card["daily_limit"],
        "issued_at": card["issued_at"],
    }


def public_virtual_card(card):
    return public_card(card)


def card_daily_spending(card):
    today = datetime.now(timezone.utc).date()

    total = Decimal("0.00")

    for transaction in card.get(
        "transactions",
        [],
    ):
        if transaction.get("type") != "CARD_PAYMENT":
            continue

        try:
            transaction_date = datetime.fromisoformat(
                transaction["created_at"]
            ).date()

            if transaction_date == today:
                total += Decimal(
                    str(transaction["amount"])
                )

        except (
            KeyError,
            TypeError,
            ValueError,
            InvalidOperation,
        ):
            continue

    return total


def public_card_transaction(transaction):
    return {
        "id": transaction["id"],
        "type": transaction["type"],
        "merchant": transaction.get(
            "merchant",
            "",
        ),
        "category": transaction.get(
            "category",
            "Other",
        ),
        "amount": str(
            transaction["amount"]
        ),
        "status": transaction.get(
            "status",
            "COMPLETED",
        ),
        "created_at": transaction["created_at"],
        "balance_after": str(
            transaction.get(
                "balance_after",
                "0.00",
            )
        ),
    }