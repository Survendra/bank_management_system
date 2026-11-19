import time
import unittest
from unittest.mock import patch

import bank_service
from app import app as flask_app


ACCOUNT_NUMBER = "66243543507"


def make_account(locked_until, failed_attempts):
    return {
        "name": "Test User",
        "age": 22,
        "email": "",
        "account_number": ACCOUNT_NUMBER,
        "balance": "100",
        "failed_attempts": failed_attempts,
        "locked_until": locked_until,
        "pin_salt": "a" * 32,
        "pin_hash": "b" * 64,
    }


class LoginLockoutTests(unittest.TestCase):
    def test_expired_lock_starts_a_new_attempt_count(self):
        account = make_account(time.time() - 1, 6)

        with (
            patch.object(
                bank_service,
                "refresh_account",
                return_value=account,
            ),
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

    def test_active_lock_rejects_login_without_another_pin_attempt(self):
        account = make_account(time.time() + 60, 3)

        with (
            patch.object(
                bank_service,
                "refresh_account",
                return_value=account,
            ),
            patch.object(bank_service, "save_data") as save_data,
            patch.object(bank_service, "verify_pin") as verify_pin,
        ):
            response = flask_app.test_client().post(
                "/api/login",
                json={"account_number": ACCOUNT_NUMBER, "pin": "1234"},
            )

        self.assertEqual(response.status_code, 423)
        self.assertEqual(account["failed_attempts"], 3)
        save_data.assert_not_called()
        verify_pin.assert_not_called()


if __name__ == "__main__":
    unittest.main()
