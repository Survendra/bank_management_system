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

ACCOUNT_FILE = os.path.join(os.path.dirname(__file__), "bank_data.json")
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

    if not storage_ready:
        return False

    data = {
        "version": 2,
        "accounts": {},
    }

    for account_number, account in accounts.items():
        record = account.copy()
        record["balance"] = str(account["balance"])
        data["accounts"][account_number] = record

    temp_path = None

    try:
        directory = os.path.dirname(os.path.abspath(ACCOUNT_FILE))

        fd, temp_path = tempfile.mkstemp(
            prefix=".bank_data_",
            suffix=".tmp",
            dir=directory,
        )

        with os.fdopen(fd, "w", encoding="utf-8") as file:
            json.dump(data, file, indent=4)
            file.flush()
            os.fsync(file.fileno())

        os.replace(temp_path, ACCOUNT_FILE)

        return True

    except (OSError, TypeError, ValueError):

        if temp_path and os.path.exists(temp_path):
            try:
                os.remove(temp_path)
            except OSError:
                pass

        return False


def load_data():
    global accounts, storage_ready

    accounts = {}

    if not os.path.exists(ACCOUNT_FILE):
        storage_ready = True
        return

    try:
        with open(ACCOUNT_FILE, "r", encoding="utf-8") as file:
            data = json.load(file)

        if not isinstance(data, dict):
            raise ValueError("Invalid JSON structure.")

        loaded = data.get("accounts")

        if loaded is None and "account_number" in data:
            loaded = {
                str(data["account_number"]): data
            }

        if not isinstance(loaded, dict):
            raise ValueError("Unknown account data format.")

        valid = {}

        for account_number, item in loaded.items():

            try:
                account_number = str(account_number)

                if (
                    not re.fullmatch(
                        r"[0-9]{11}",
                        account_number,
                    )
                    or not isinstance(item, dict)
                ):
                    print(f"REJECTED {account_number}: invalid account number or data")
                    continue

                name = item["name"]
                age = item["age"]

                balance_value = Decimal(
                    str(item["balance"])
                )

                if not is_valid_name(name):
                    print(f"REJECTED {account_number}: invalid name = {name!r}")
                    continue

                if (
                    isinstance(age, bool)
                    or not isinstance(age, int)
                    or not 18 <= age <= 120
                ):
                    print(f"REJECTED {account_number}: invalid age = {age!r}")
                    continue

                if (
                    not balance_value.is_finite()
                    or balance_value < 0
                ):
                    print(
                        f"REJECTED {account_number}: invalid balance = {balance_value!r}"
                    )
                    continue

                # Email was not present in older accounts.
                # Those accounts will automatically use an empty email.
                email = str(
                    item.get("email", "")
                ).strip()

                record = {
                    "name": name,
                    "age": age,
                    "email": email,
                    "account_number": account_number,
                    "balance": balance_value,
                    "failed_attempts": item.get(
                        "failed_attempts",
                        0,
                    ),
                    "locked_until": float(
                        item.get("locked_until", 0)
                    ),
                    "transactions": item.get(
                        "transactions",
                        [],
                    ),
                    "beneficiaries": item.get(
                        "beneficiaries",
                        [],
                    ),
                    "notifications": item.get(
                        "notifications",
                        [],
                    ),
                    "security_activity": item.get(
                        "security_activity",
                        [],
                    ),
                    "cards": item.get(
                        "cards",
                        [],
                    ),
                    "virtual_cards": item.get(
                        "virtual_cards",
                        [],
                    ),
                    "two_factor": item.get(
                        "two_factor",
                        {
                            "enabled": False,
                            "secret": None,
                        },
                    ),
                }

                if not isinstance(
                    record["beneficiaries"],
                    list,
                ):
                    record["beneficiaries"] = []

                if not isinstance(
                    record["transactions"],
                    list,
                ):
                    record["transactions"] = []

                if not isinstance(
                    record["notifications"],
                    list,
                ):
                    record["notifications"] = []

                if not isinstance(
                    record["security_activity"],
                    list,
                ):
                    record["security_activity"] = []

                if not isinstance(
                    record["cards"],
                    list,
                ):
                    record["cards"] = []

                if not isinstance(
                    record["virtual_cards"],
                    list,
                ):
                    record["virtual_cards"] = []

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
                    record["two_factor"].get("secret") is not None
                    and not isinstance(
                        record["two_factor"].get("secret"),
                        str,
                    )
                ):
                    record["two_factor"]["secret"] = None

                salt = item.get("pin_salt")
                pin_hash = item.get("pin_hash")

                if (salt is None) != (pin_hash is None):
                    print(f"PIN FIELD MISMATCH: {account_number}")
                    continue

                if salt is not None:

                    if not re.fullmatch(
                        r"[0-9a-f]{32}",
                        str(salt),
                    ):
                        print(f"INVALID PIN SALT: {account_number} | {salt}")
                        continue

                    if not re.fullmatch(
                        r"[0-9a-f]{64}",
                        str(pin_hash),
                    ):
                        print(
                            f"INVALID PIN HASH: {account_number} | "
                            f"type={type(pin_hash).__name__} | "
                            f"length={len(str(pin_hash))}"
                        )
                        continue

                    record["pin_salt"] = salt
                    record["pin_hash"] = pin_hash

                attempts = record["failed_attempts"]

                if (
                    isinstance(attempts, bool)
                    or not isinstance(attempts, int)
                    or attempts < 0
                ):
                    continue

                if (
                    not math.isfinite(
                        record["locked_until"]
                    )
                    or record["locked_until"] < 0
                ):
                    continue

                if (
                    0 < record["locked_until"] <= time.time()
                ):
                    record["failed_attempts"] = 0
                    record["locked_until"] = 0
                elif attempts > MAX_PIN_ATTEMPTS:
                    record["failed_attempts"] = MAX_PIN_ATTEMPTS

                valid[account_number] = record

            except (
                KeyError,
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

        if (
            "account_number" in data
            and "accounts" not in data
        ):
            save_data()

    except (
        OSError,
        json.JSONDecodeError,
        TypeError,
        ValueError,
    ):
        storage_ready = False
        accounts = {}


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