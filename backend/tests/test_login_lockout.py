import json
import os
import tempfile
import time
import unittest
from unittest.mock import patch

import bank_service
from app import app as flask_app


ACCOUNT_NUMBER = "66243543507"


class LoginLockoutTests(unittest.TestCase):
    def test_expired_lock_with_stale_attempts_does_not_reject_account(self):
        account_data = {
            "name": "Test User",
            "age": 22,
            "account_number": ACCOUNT_NUMBER,
            "balance": "100",
            "failed_attempts": 6,
            "locked_until": time.time() - 1,
            "pin_salt": "a" * 32,
            "pin_hash": "b" * 64,
        }

        with tempfile.TemporaryDirectory() as directory:
            data_file = os.path.join(directory, "bank_data.json")
            with open(data_file, "w", encoding="utf-8") as file:
                json.dump({"accounts": {ACCOUNT_NUMBER: account_data}}, file)

            with (
                patch.object(bank_service, "ACCOUNT_FILE", data_file),
                patch.dict(bank_service.accounts, {}, clear=True),
                patch.object(bank_service, "storage_ready", False),
            ):
                bank_service.load_data()

                self.assertIn(ACCOUNT_NUMBER, bank_service.accounts)
                self.assertEqual(
                    bank_service.accounts[ACCOUNT_NUMBER]["failed_attempts"],
                    0,
                )
                self.assertEqual(
                    bank_service.accounts[ACCOUNT_NUMBER]["locked_until"],
                    0,
                )

    def test_login_starts_new_attempt_count_after_lock_expires(self):
        account = {
            "name": "Test User",
            "age": 22,
            "email": "",
            "account_number": ACCOUNT_NUMBER,
            "balance": 100,
            "failed_attempts": 6,
            "locked_until": time.time() - 1,
            "pin_salt": "a" * 32,
            "pin_hash": "b" * 64,
        }

        with (
            patch.dict(bank_service.accounts, {ACCOUNT_NUMBER: account}, clear=True),
            patch.object(bank_service, "save_data", return_value=True),
            patch.object(bank_service, "verify_pin", return_value=False),
        ):
            response = flask_app.test_client().post(
                "/api/login",
                json={"account_number": ACCOUNT_NUMBER, "pin": "1234"},
            )

        self.assertEqual(response.status_code, 401)
        self.assertEqual(account["failed_attempts"], 1)
        self.assertEqual(account["locked_until"], 0)


if __name__ == "__main__":
    unittest.main()
