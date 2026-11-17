import time
import unittest
from decimal import Decimal
from unittest.mock import patch

import bank_service
from app import app as flask_app


ACCOUNT_NUMBER = "66243543507"
RECIPIENT_NUMBER = "55446677889"
MAX_TRANSACTION_AMOUNT = "5000000000.00"


class TransactionAmountLimitTests(unittest.TestCase):
    def setUp(self):
        self.account = {
            "name": "Test User",
            "age": 22,
            "email": "",
            "account_number": ACCOUNT_NUMBER,
            "balance": Decimal("6000000000.00"),
            "transactions": [],
            "notifications": [],
            "beneficiaries": [
                {
                    "beneficiary_id": "BEN-TEST",
                    "name": "Recipient User",
                    "account_number": RECIPIENT_NUMBER,
                }
            ],
            "pin_salt": "a" * 32,
            "pin_hash": "b" * 64,
            "failed_attempts": 0,
            "locked_until": 0,
        }
        self.recipient = {
            "name": "Recipient User",
            "account_number": RECIPIENT_NUMBER,
            "balance": Decimal("0.00"),
            "transactions": [],
            "notifications": [],
        }
        self.accounts_patch = patch.dict(
            bank_service.accounts,
            {
                ACCOUNT_NUMBER: self.account,
                RECIPIENT_NUMBER: self.recipient,
            },
            clear=True,
        )
        self.accounts_patch.start()
        self.save_data_patch = patch.object(
            bank_service,
            "save_data",
            return_value=True,
        )
        self.save_data = self.save_data_patch.start()
        self.verify_pin_patch = patch.object(
            bank_service,
            "verify_pin",
            return_value=True,
        )
        self.verify_pin_patch.start()

        self.client = flask_app.test_client()
        with self.client.session_transaction() as session:
            session["account_number"] = ACCOUNT_NUMBER
            session["login_time"] = time.time()
            session["last_activity"] = time.time()

    def tearDown(self):
        self.verify_pin_patch.stop()
        self.save_data_patch.stop()
        self.accounts_patch.stop()

    def test_amount_over_500_crore_is_rejected_for_all_transaction_routes(self):
        requests = (
            ("/api/deposit", {"amount": "5000000000.01"}),
            ("/api/withdraw", {"amount": "5000000000.01"}),
            (
                "/api/transfer",
                {
                    "amount": "5000000000.01",
                    "beneficiary_id": "BEN-TEST",
                    "pin": "1234",
                },
            ),
        )

        for endpoint, payload in requests:
            with self.subTest(endpoint=endpoint):
                response = self.client.post(endpoint, json=payload)

                self.assertEqual(response.status_code, 400)
                self.assertEqual(
                    response.get_json()["message"],
                    "Transaction amount cannot exceed 500 crore.",
                )

        self.assertEqual(self.account["balance"], Decimal("6000000000.00"))
        self.assertEqual(self.recipient["balance"], Decimal("0.00"))
        self.save_data.assert_not_called()

    def test_amount_of_500_crore_is_accepted_for_all_transaction_routes(self):
        requests = (
            ("/api/deposit", {"amount": MAX_TRANSACTION_AMOUNT}),
            ("/api/withdraw", {"amount": MAX_TRANSACTION_AMOUNT}),
            (
                "/api/transfer",
                {
                    "amount": MAX_TRANSACTION_AMOUNT,
                    "beneficiary_id": "BEN-TEST",
                    "pin": "4826",
                },
            ),
        )

        for endpoint, payload in requests:
            with self.subTest(endpoint=endpoint):
                self.account["balance"] = Decimal("6000000000.00")
                self.account["transactions"] = []
                self.account["notifications"] = []
                self.recipient["balance"] = Decimal("0.00")
                self.recipient["transactions"] = []
                self.recipient["notifications"] = []
                self.save_data.reset_mock()

                response = self.client.post(endpoint, json=payload)

                self.assertEqual(response.status_code, 200)
                self.save_data.assert_called_once()


if __name__ == "__main__":
    unittest.main()
