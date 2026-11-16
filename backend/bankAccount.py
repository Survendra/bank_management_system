
import os
import re
import json
import time
import hmac
import math
import secrets
import hashlib
import getpass
import tempfile

from decimal import Decimal, InvalidOperation


# ==================================================
# GLOBAL CONFIGURATION
# ==================================================

accounts = {}
active_account = None

ACCOUNT_FILE = "bank_data.json"

MAX_PIN_ATTEMPTS = 3
LOCK_DURATION = 60
PIN_ITERATIONS = 600000

storage_ready = False


# ==================================================
# NAME VALIDATION
# ==================================================

def isValidName(name):

    pattern = r"[A-Za-z]+(?:[ .'-][A-Za-z]+)*"

    return bool(re.fullmatch(pattern, name))


def getValidName():

    while True:

        name = input("Enter your name: ").strip()

        if not name:
            print("Name cannot be empty.")
            continue

        if not isValidName(name):
            print("Invalid name! Use letters, spaces, hyphens or apostrophes only.")
            continue

        return " ".join(name.split())


# ==================================================
# AGE VALIDATION
# ==================================================

def getValidAge():

    while True:

        age = input("Enter your age: ").strip()

        if not re.fullmatch(r"[0-9]+", age):
            print("Age must contain positive whole numbers only.")
            continue

        age = int(age)

        if age < 18:
            print("You must be at least 18 years old.")
            continue

        if age > 120:
            print("Please enter a realistic age.")
            continue

        return age


# ==================================================
# AMOUNT VALIDATION
# ==================================================

def getValidAmount(message):

    while True:

        amount = input(message).strip()

        if not re.fullmatch(r"[0-9]+(?:\.[0-9]{1,2})?", amount):
            print("Invalid amount! Example: 500 or 500.50")
            continue

        try:

            value = Decimal(amount)

            if not value.is_finite():
                print("Amount must be finite.")
                continue

            if value <= 0:
                print("Amount must be greater than zero.")
                continue

            return value

        except InvalidOperation:
            print("Invalid amount. Please try again.")


# ==================================================
# PIN VALIDATION
# ==================================================

def isStrongPIN(pin):

    if not re.fullmatch(r"[0-9]{4}", pin):
        return False

    # Reject repeated digits
    if len(set(pin)) == 1:
        return False

    # Reject sequential PINs
    weak_pins = {
        "0123", "1234", "2345", "3456",
        "4567", "5678", "6789",
        "9876", "8765", "7654", "6543",
        "5432", "4321", "3210"
    }

    if pin in weak_pins:
        return False

    # Reject common PINs
    common_pins = {
        "0000", "1111", "2222", "3333",
        "4444", "5555", "6666", "7777",
        "8888", "9999", "1212", "1122",
        "1004", "2000", "2020", "2580"
    }

    if pin in common_pins:
        return False

    return True


def getValidPIN():

    while True:

        pin = getpass.getpass("Create your 4-digit PIN: ")

        if not isStrongPIN(pin):
            print("Weak PIN! Choose a different 4-digit PIN.")
            continue

        confirm_pin = getpass.getpass("Confirm your PIN: ")

        if not hmac.compare_digest(pin, confirm_pin):
            print("PINs do not match. Try again.")
            continue

        return pin


# ==================================================
# PIN HASHING
# ==================================================

def hashPIN(pin, salt=None):

    if salt is None:
        salt = secrets.token_bytes(16).hex()

    hashed_pin = hashlib.pbkdf2_hmac(
        "sha256",
        pin.encode("utf-8"),
        bytes.fromhex(salt),
        PIN_ITERATIONS
    ).hex()

    return salt, hashed_pin


def verifyPIN(pin, salt, stored_hash):

    _, entered_hash = hashPIN(pin, salt)

    return hmac.compare_digest(
        entered_hash,
        stored_hash
    )


# ==================================================
# SAVE DATA - ATOMIC FILE WRITING
# ==================================================

def saveData():

    global storage_ready

    if not storage_ready:
        print("Storage unavailable. Changes cannot be saved.")
        return False

    data = {
        "version": 2,
        "accounts": {}
    }

    for account_number, account in accounts.items():

        record = account.copy()

        # Store money as a string for exact decimal precision
        record["balance"] = str(account["balance"])

        data["accounts"][account_number] = record

    temp_path = None

    try:

        directory = os.path.dirname(os.path.abspath(ACCOUNT_FILE))

        fd, temp_path = tempfile.mkstemp(
            prefix=".bank_data_",
            suffix=".tmp",
            dir=directory
        )

        with os.fdopen(fd, "w", encoding="utf-8") as file:

            json.dump(data, file, indent=4)

            file.flush()
            os.fsync(file.fileno())

        # Replace the old file only after writing succeeds
        os.replace(temp_path, ACCOUNT_FILE)

        return True

    except (OSError, TypeError, ValueError) as error:

        print(f"Data saving failed: {error}")

        if temp_path and os.path.exists(temp_path):

            try:
                os.remove(temp_path)
            except OSError:
                pass

        return False


# ==================================================
# LOAD AND VALIDATE DATA
# ==================================================

def loadData():

    global accounts, active_account, storage_ready

    accounts = {}
    active_account = None

    if not os.path.exists(ACCOUNT_FILE):

        storage_ready = True
        print("No previous account data found.")
        return

    try:

        with open(ACCOUNT_FILE, "r", encoding="utf-8") as file:
            data = json.load(file)

        if not isinstance(data, dict):
            raise ValueError("Invalid JSON structure.")

        # Current multi-account format
        if "accounts" in data:

            loaded_accounts = data["accounts"]

            if not isinstance(loaded_accounts, dict):
                raise ValueError("Invalid accounts structure.")

            valid_accounts = {}
            skipped = 0

            for acc_no, account in loaded_accounts.items():

                try:

                    acc_no = str(acc_no)

                    if not re.fullmatch(r"[0-9]{11}", acc_no):
                        raise ValueError("Invalid account number.")

                    if not isinstance(account, dict):
                        raise ValueError("Invalid account record.")

                    name = account["name"]
                    age = account["age"]
                    balance = Decimal(str(account["balance"]))

                    if not isinstance(name, str) or not isValidName(name):
                        raise ValueError("Invalid account name.")

                    if (
                        isinstance(age, bool)
                        or not isinstance(age, int)
                        or not 18 <= age <= 120
                    ):
                        raise ValueError("Invalid age.")

                    if not balance.is_finite() or balance < 0:
                        raise ValueError("Invalid balance.")

                    record = {
                        "name": name,
                        "age": age,
                        "account_number": acc_no,
                        "balance": balance
                    }

                    # PIN fields must either both exist or both be absent
                    salt = account.get("pin_salt")
                    pin_hash = account.get("pin_hash")

                    if (salt is None) != (pin_hash is None):
                        raise ValueError("Incomplete PIN credentials.")

                    if salt is not None:

                        if not isinstance(salt, str) or not re.fullmatch(
                            r"[0-9a-f]{32}", salt
                        ):
                            raise ValueError("Invalid PIN salt.")

                        if not isinstance(pin_hash, str) or not re.fullmatch(
                            r"[0-9a-f]{64}", pin_hash
                        ):
                            raise ValueError("Invalid PIN hash.")

                        record["pin_salt"] = salt
                        record["pin_hash"] = pin_hash

                    attempts = account.get("failed_attempts", 0)

                    if (
                        isinstance(attempts, bool)
                        or not isinstance(attempts, int)
                        or not 0 <= attempts <= MAX_PIN_ATTEMPTS
                    ):
                        raise ValueError("Invalid failed attempt count.")

                    locked_until = float(account.get("locked_until", 0))

                    if not math.isfinite(locked_until) or locked_until < 0:
                        raise ValueError("Invalid lock timestamp.")

                    record["failed_attempts"] = attempts
                    record["locked_until"] = locked_until

                    valid_accounts[acc_no] = record

                except (KeyError, TypeError, ValueError, InvalidOperation):
                    skipped += 1
                    continue

            accounts = valid_accounts

            if skipped:
                print(f"Warning: {skipped} invalid account record(s) skipped.")

        # Legacy single-account format
        elif "account_number" in data:

            acc_no = str(data["account_number"])

            if not re.fullmatch(r"[0-9]{11}", acc_no):
                raise ValueError("Invalid legacy account number.")

            name = data["name"]
            age = int(data["age"])
            balance = Decimal(str(data["balance"]))

            if not isinstance(name, str) or not isValidName(name):
                raise ValueError("Invalid legacy account name.")

            if not 18 <= age <= 120:
                raise ValueError("Invalid legacy age.")

            if not balance.is_finite() or balance < 0:
                raise ValueError("Invalid legacy balance.")

            accounts[acc_no] = {
                "name": name,
                "age": age,
                "account_number": acc_no,
                "balance": balance,
                "failed_attempts": 0,
                "locked_until": 0
            }

        else:

            raise ValueError("Unknown account data format.")

        storage_ready = True

        print(f"\nSuccessfully loaded {len(accounts)} account(s).")
        print("Please login to continue.")

        # Save migrated legacy data in the new format
        if "account_number" in data and "accounts" not in data:
            saveData()

    except (
        OSError,
        json.JSONDecodeError,
        KeyError,
        TypeError,
        ValueError,
        InvalidOperation
    ) as error:

        storage_ready = False

        print("\nUnable to load account data.")
        print(f"Reason: {error}")
        print("Storage has been disabled to prevent accidental data loss.")


# ==================================================
# GENERATE UNIQUE ACCOUNT NUMBER
# ==================================================

def generateAccountNumber():

    while True:

        account_number = str(
            secrets.randbelow(90000000000) + 10000000000
        )

        if account_number not in accounts:
            return account_number


# ==================================================
# GET ACTIVE ACCOUNT
# ==================================================

def getActiveAccount():

    if not storage_ready:
        print("Account storage is unavailable.")
        return None

    if active_account is None:
        print("Please login to your account first.")
        return None

    if active_account not in accounts:
        print("Account not found.")
        return None

    return accounts[active_account]


# ==================================================
# ACCOUNT LOCK CHECK
# ==================================================

def checkAccountLock(account):

    current_time = time.time()
    locked_until = account.get("locked_until", 0)

    if current_time < locked_until:

        remaining = math.ceil(locked_until - current_time)

        print("\nAccount temporarily locked!")
        print(f"Try again after {remaining} seconds.")

        return False

    # Reset expired lockout
    if locked_until > 0:

        old_attempts = account["failed_attempts"]
        account["failed_attempts"] = 0
        account["locked_until"] = 0

        if not saveData():

            account["failed_attempts"] = old_attempts
            account["locked_until"] = locked_until

            print("Unable to reset security status. Please try later.")
            return False

    return True


# ==================================================
# RECORD FAILED PIN ATTEMPT
# ==================================================

def recordFailedAttempt(account):

    old_attempts = account["failed_attempts"]
    old_lock = account["locked_until"]

    account["failed_attempts"] += 1

    if account["failed_attempts"] >= MAX_PIN_ATTEMPTS:

        account["locked_until"] = time.time() + LOCK_DURATION

    if not saveData():

        # Keep the account blocked in memory if saving fails
        account["failed_attempts"] = MAX_PIN_ATTEMPTS
        account["locked_until"] = max(
            old_lock,
            time.time() + LOCK_DURATION
        )

        print("Security status could not be saved.")
        print("Access denied as a precaution.")

        return False

    remaining = MAX_PIN_ATTEMPTS - account["failed_attempts"]

    if remaining > 0:

        print("Incorrect PIN!")
        print(f"Attempts remaining: {remaining}")

    else:

        print("\nMaximum incorrect attempts reached!")
        print("Account locked for 60 seconds.")

    return True


# ==================================================
# VERIFY PIN WITH LOCKOUT
# ==================================================

def verifyAccountPIN(account):

    if not checkAccountLock(account):
        return False

    pin = getpass.getpass("Enter your 4-digit PIN: ")

    if not re.fullmatch(r"[0-9]{4}", pin):

        print("Invalid PIN format.")
        recordFailedAttempt(account)
        return False

    if not verifyPIN(
        pin,
        account["pin_salt"],
        account["pin_hash"]
    ):

        recordFailedAttempt(account)
        return False

    # Correct PIN: reset failed attempts
    old_attempts = account["failed_attempts"]
    old_lock = account["locked_until"]

    account["failed_attempts"] = 0
    account["locked_until"] = 0

    if not saveData():

        account["failed_attempts"] = old_attempts
        account["locked_until"] = old_lock

        print("Unable to verify security status.")
        print("Login denied.")

        return False

    return True


# ==================================================
# OPEN NEW ACCOUNT
# ==================================================

def openAcc():

    if not storage_ready:
        print("Cannot create an account while storage is unavailable.")
        return

    print("\n========== OPEN NEW ACCOUNT ==========")

    name = getValidName()
    age = getValidAge()

    print("\n========== CREATE ACCOUNT PIN ==========")

    pin = getValidPIN()

    salt, pin_hash = hashPIN(pin)

    account_number = generateAccountNumber()

    if account_number in accounts:
        print("Duplicate account number detected.")
        return

    accounts[account_number] = {
        "name": name,
        "age": age,
        "account_number": account_number,
        "balance": Decimal("0.00"),
        "pin_salt": salt,
        "pin_hash": pin_hash,
        "failed_attempts": 0,
        "locked_until": 0
    }

    if not saveData():

        del accounts[account_number]

        print("Account creation failed.")
        return

    print("\nAccount created successfully!")
    print(f"Name: {name}")
    print(f"Age: {age}")
    print(f"Account Number: {account_number}")
    print("Initial Balance: $0.00")

    print("\nPlease login using your account number and PIN.")


# ==================================================
# ACCOUNT LOGIN
# ==================================================

def login():

    global active_account

    if not storage_ready:
        print("Account storage is unavailable.")
        return

    if not accounts:
        print("No registered accounts found.")
        return

    if active_account is not None:
        print("An account is already logged in. Logout first.")
        return

    print("\n========== ACCOUNT LOGIN ==========")

    account_number = input("Enter account number: ").strip()

    if not re.fullmatch(r"[0-9]{11}", account_number):

        print("Account number must contain exactly 11 digits.")
        return

    if account_number not in accounts:

        print("Account not found.")
        return

    account = accounts[account_number]

    # Legacy account without PIN
    if "pin_hash" not in account:

        print("\nThis is an older account without PIN protection.")
        print("For this local practice project, create a PIN now.")
        print("Account number alone does not verify your identity.")

        pin = getValidPIN()
        salt, pin_hash = hashPIN(pin)

        account["pin_salt"] = salt
        account["pin_hash"] = pin_hash

        if not saveData():

            del account["pin_salt"]
            del account["pin_hash"]

            print("PIN setup failed.")
            return

        print("PIN created successfully!")

    else:

        if not verifyAccountPIN(account):
            return

    active_account = account_number

    print("\nLogin successful!")
    print(f"Welcome, {account['name']}!")


# ==================================================
# LOGOUT
# ==================================================

def logout():

    global active_account

    if active_account is None:

        print("No account is currently logged in.")
        return

    print(f"Goodbye, {accounts[active_account]['name']}!")

    active_account = None

    print("Logout successful!")


# ==================================================
# CHANGE PIN
# ==================================================

def changePIN():

    account = getActiveAccount()

    if account is None:
        return

    print("\n========== CHANGE PIN ==========")

    if not verifyAccountPIN(account):

        if account["locked_until"] > time.time():

            print("Account locked. Logging out for safety.")
            logout()

        return

    print("\nEnter your new PIN.")

    new_pin = getValidPIN()

    if verifyPIN(
        new_pin,
        account["pin_salt"],
        account["pin_hash"]
    ):

        print("New PIN cannot be the same as the old PIN.")
        return

    old_salt = account["pin_salt"]
    old_hash = account["pin_hash"]

    new_salt, new_hash = hashPIN(new_pin)

    account["pin_salt"] = new_salt
    account["pin_hash"] = new_hash

    if not saveData():

        account["pin_salt"] = old_salt
        account["pin_hash"] = old_hash

        print("PIN update failed.")
        return

    print("PIN changed successfully!")


# ==================================================
# DEPOSIT
# ==================================================

def deposit():

    account = getActiveAccount()

    if account is None:
        return

    amount = getValidAmount("Enter amount to deposit: ")

    old_balance = account["balance"]
    account["balance"] += amount

    if not saveData():

        account["balance"] = old_balance

        print("Deposit failed. No changes were saved.")
        return

    print(f"Successfully deposited ${amount:.2f}")

    balanceInquiry()


# ==================================================
# WITHDRAW
# ==================================================

def withdraw():

    account = getActiveAccount()

    if account is None:
        return

    amount = getValidAmount("Enter amount to withdraw: ")

    if amount > account["balance"]:

        print("Insufficient funds.")
        print(f"Available balance: ${account['balance']:.2f}")

        return

    old_balance = account["balance"]
    account["balance"] -= amount

    if not saveData():

        account["balance"] = old_balance

        print("Withdrawal failed. No changes were saved.")
        return

    print(f"Successfully withdrew ${amount:.2f}")

    balanceInquiry()


# ==================================================
# BALANCE INQUIRY
# ==================================================

def balanceInquiry():

    account = getActiveAccount()

    if account is None:
        return

    print("\n========== BALANCE INQUIRY ==========")

    print(f"Account Holder: {account['name']}")
    print(f"Account Number: {account['account_number']}")
    print(f"Available Balance: ${account['balance']:.2f}")


# ==================================================
# ACCOUNT DETAILS
# ==================================================

def accountDetails():

    account = getActiveAccount()

    if account is None:
        return

    print("\n========== ACCOUNT DETAILS ==========")

    print(f"Name: {account['name']}")
    print(f"Age: {account['age']}")
    print(f"Account Number: {account['account_number']}")
    print(f"Balance: ${account['balance']:.2f}")
    print("PIN: ********")


# ==================================================
# MAIN MENU
# ==================================================

def main():

    loadData()

    switcher = {

        1: openAcc,
        2: login,
        3: deposit,
        4: withdraw,
        5: balanceInquiry,
        6: accountDetails,
        7: changePIN,
        8: logout

    }

    while True:

        print("\n========================================")
        print("       BANK MANAGEMENT SYSTEM")
        print("========================================")

        if active_account in accounts:

            print(f"Logged In: {accounts[active_account]['name']}")
            print(f"Account Number: {active_account}")

        else:

            print("Status: Not Logged In")

        print("\n1. Open New Account")
        print("2. Login")
        print("3. Deposit Funds")
        print("4. Withdraw Funds")
        print("5. Check Balance")
        print("6. Account Details")
        print("7. Change PIN")
        print("8. Logout")
        print("9. Exit")

        try:

            choice = input("\nEnter your choice: ").strip()

        except (EOFError, KeyboardInterrupt):

            print("\nApplication closed safely.")
            break

        if not re.fullmatch(r"[0-9]+", choice):

            print("Invalid input! Enter a menu number.")
            continue

        choice = int(choice)

        if choice == 9:

            print("Thank you for using our banking system!")
            break

        if choice not in switcher:

            print("Invalid choice! Select between 1 and 9.")
            continue

        try:

            switcher[choice]()

        except (EOFError, KeyboardInterrupt):

            print("\nOperation cancelled safely.")

        except Exception as error:

            print(f"\nUnexpected error: {error}")
            print("Please try again.")


# ==================================================
# APPLICATION ENTRY POINT
# ==================================================

if __name__ == "__main__":

    try:
        main()

    except KeyboardInterrupt:
        print("\nApplication terminated safely.")

    except Exception as error:
        print(f"\nApplication error: {error}")
