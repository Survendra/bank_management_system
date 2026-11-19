import copy
import os
import time
import unittest
from decimal import Decimal
from datetime import datetime, timedelta, timezone
from types import SimpleNamespace
from unittest.mock import patch
from werkzeug.security import check_password_hash, generate_password_hash
from pymongo.errors import AutoReconnect

import bank_service
import app as app_module
from app import (
    app as flask_app,
    _next_schedule_occurrence,
    _process_claimed_scheduled_transfer,
    configured_staff_users,
)


ACCOUNT_NUMBER = "66243543507"
RECIPIENT_NUMBER = "55446677889"


class NoopMongoTransaction:
    def __enter__(self):
        return self

    def __exit__(self, exception_type, exception, traceback):
        return False

    def start_transaction(self):
        return self


class FeatureEndpointTests(unittest.TestCase):
    def setUp(self):
        self.account = {
            "name": "Test User",
            "age": 22,
            "email": "",
            "account_number": ACCOUNT_NUMBER,
            "balance": Decimal("100.00"),
            "transactions": [],
            "notifications": [],
            "beneficiaries": [{
                "beneficiary_id": "BEN-TEST",
                "name": "Recipient User",
                "account_number": RECIPIENT_NUMBER,
            }],
            "savings_goals": [],
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
        self.save_data_mock = self.save_data_patch.start()
        self.verify_pin_patch = patch.object(
            bank_service,
            "verify_pin",
            return_value=True,
        )
        self.verify_pin_patch.start()
        self.client = flask_app.test_client()
        with self.client.session_transaction() as browser_session:
            browser_session["account_number"] = ACCOUNT_NUMBER
            browser_session["login_time"] = time.time()
            browser_session["last_activity"] = time.time()

    def tearDown(self):
        self.verify_pin_patch.stop()
        self.save_data_patch.stop()
        self.accounts_patch.stop()

    def test_failed_withdrawal_is_visible_without_changing_balance(self):
        response = self.client.post("/api/withdraw", json={"amount": "125.00"})

        self.assertEqual(response.status_code, 400)
        self.assertEqual(self.account["balance"], Decimal("100.00"))
        self.assertEqual(self.account["transactions"][0]["status"], "FAILED")
        self.save_data_mock.assert_called_once()

    def test_savings_allocation_reduces_available_transfer_funds(self):
        self.account["savings_goals"] = [{
            "id": "GOAL-TEST",
            "name": "Emergency fund",
            "target_amount": "500.00",
            "saved_amount": "25.00",
        }]

        response = self.client.post(
            "/api/transfer",
            json={
                "beneficiary_id": "BEN-TEST",
                "amount": "80.00",
                "pin": "4826",
            },
        )

        self.assertEqual(response.status_code, 400)
        self.assertEqual(self.account["balance"], Decimal("100.00"))
        self.assertEqual(self.recipient["balance"], Decimal("0.00"))
        self.assertEqual(self.account["transactions"][0]["status"], "FAILED")

    def test_non_staff_cannot_read_staff_dispute_queue(self):
        response = self.client.get("/api/staff/disputes")

        self.assertEqual(response.status_code, 403)

    def test_openapi_document_lists_staff_and_transaction_endpoints(self):
        response = self.client.get("/openapi.json")

        self.assertEqual(response.status_code, 200)
        document = response.get_json()
        self.assertEqual(document["openapi"], "3.0.3")
        self.assertIn("/api/transactions/{transaction_id}/dispute", document["paths"])
        self.assertIn("/api/staff/disputes/{dispute_id}", document["paths"])
        self.assertIn("/api/staff/users", document["paths"])
        self.assertIn("get", document["paths"]["/api/staff/users"])
        self.assertIn("post", document["paths"]["/api/staff/users"])

    def test_swagger_ui_is_available_at_docs(self):
        response = self.client.get("/docs", follow_redirects=True)

        self.assertEqual(response.status_code, 200)
        self.assertIn("text/html", response.content_type)

    def test_staff_login_requires_a_configured_flask_secret(self):
        with patch.dict(
            flask_app.config,
            {"SECRET_KEY": "change-this-development-secret"},
        ):
            response = self.client.post(
                "/api/staff/login",
                json={"username": "staff", "password": "password"},
            )

        self.assertEqual(response.status_code, 503)

    def test_submitted_dispute_response_does_not_include_mongo_id(self):
        self.account["transactions"] = [{
            "id": "TX-DISPUTE",
            "type": "CARD_PAYMENT",
            "amount": "12.50",
            "status": "COMPLETED",
        }]

        def insert_dispute(document, **kwargs):
            document["_id"] = object()

        with (
            patch.object(
                bank_service.disputes_collection,
                "find_one",
                return_value=None,
            ),
            patch.object(
                bank_service.disputes_collection,
                "insert_one",
                side_effect=insert_dispute,
            ),
            patch.object(
                bank_service.mongo_client,
                "start_session",
                return_value=NoopMongoTransaction(),
            ),
            patch.object(bank_service, "save_accounts_atomic"),
            patch.object(bank_service, "mark_accounts_persisted"),
            patch.object(bank_service.audit_log_collection, "insert_one"),
        ):
            response = self.client.post(
                "/api/transactions/TX-DISPUTE/dispute",
                json={"issue": "OTHER", "notes": ""},
            )

        self.assertEqual(response.status_code, 201)
        self.assertNotIn("_id", response.get_json()["dispute"])

    def test_revoked_server_session_is_rejected_before_account_access(self):
        client = flask_app.test_client()
        with client.session_transaction() as browser_session:
            browser_session["account_number"] = ACCOUNT_NUMBER
            browser_session["session_role"] = "customer"
            browser_session["server_session_id"] = "revoked-session"
            browser_session["login_time"] = time.time()
            browser_session["last_activity"] = time.time()
        with patch.object(
            bank_service.sessions_collection,
            "find_one",
            return_value=None,
        ):
            response = client.get("/api/account")

        self.assertEqual(response.status_code, 401)
        self.assertTrue(response.get_json()["session_expired"])

    def test_customer_can_list_and_revoke_only_an_own_device_session(self):
        class FakeCursor(list):
            def sort(self, key, direction):
                return self

        sessions = [{
            "_id": "session-1",
            "account_number": ACCOUNT_NUMBER,
            "role": "customer",
            "device": "Windows",
            "browser": "Chrome",
            "created_at": "2026-01-01T10:00:00+00:00",
            "last_seen_at": "2026-01-01T11:00:00+00:00",
        }]
        with (
            patch.object(
                bank_service.sessions_collection,
                "find",
                return_value=FakeCursor(sessions),
            ),
            patch.object(
                bank_service.sessions_collection,
                "update_one",
                return_value=SimpleNamespace(matched_count=1),
            ) as revoke,
        ):
            response = self.client.get("/api/sessions")
            revoke_response = self.client.delete("/api/sessions/session-1")

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.get_json()["sessions"][0]["device"], "Windows")
        self.assertEqual(revoke_response.status_code, 200)
        self.assertEqual(
            revoke.call_args.args[0]["account_number"],
            ACCOUNT_NUMBER,
        )

    def test_savings_contribution_reserves_funds_without_changing_total_balance(self):
        self.account["savings_goals"] = [{
            "id": "GOAL-TEST",
            "name": "Emergency fund",
            "target_amount": "500.00",
            "saved_amount": "20.00",
        }]

        response = self.client.post(
            "/api/savings-goals/GOAL-TEST/contribute",
            json={"amount": "30.00"},
        )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(self.account["balance"], Decimal("100.00"))
        self.assertEqual(self.account["savings_goals"][0]["saved_amount"], "50.00")
        self.assertEqual(response.get_json()["available_balance"], "50.00")

    def test_savings_goal_target_is_bounded_and_target_date_is_iso_date(self):
        oversized = self.client.post(
            "/api/savings-goals",
            json={"name": "Large goal", "target_amount": "5000000000.01"},
        )
        malformed_date = self.client.post(
            "/api/savings-goals",
            json={
                "name": "Invalid date",
                "target_amount": "100.00",
                "target_date": "2026-W48-4",
            },
        )

        self.assertEqual(oversized.status_code, 400)
        self.assertEqual(malformed_date.status_code, 400)
        self.assertEqual(self.account["savings_goals"], [])
        self.save_data_mock.assert_not_called()

    def test_savings_goal_changes_enforce_amount_and_remaining_target(self):
        self.account["balance"] = Decimal("6100000000.00")
        self.account["savings_goals"] = [{
            "id": "GOAL-TEST",
            "name": "Emergency fund",
            "target_amount": "6000000000.00",
            "saved_amount": "5500000000.00",
        }]

        over_limit = self.client.post(
            "/api/savings-goals/GOAL-TEST/contribute",
            json={"amount": "5000000000.01"},
        )
        over_target = self.client.post(
            "/api/savings-goals/GOAL-TEST/contribute",
            json={"amount": "500000000.01"},
        )

        self.assertEqual(over_limit.status_code, 400)
        self.assertEqual(over_target.status_code, 400)
        self.assertEqual(
            self.account["savings_goals"][0]["saved_amount"],
            "5500000000.00",
        )
        self.assertEqual(self.account["transactions"], [])
        self.save_data_mock.assert_not_called()

    def test_card_pin_failures_use_the_account_lockout(self):
        now = datetime.now(timezone.utc)
        self.account["cards"] = [{
            "id": "CARD-TEST",
            "status": "ACTIVE",
            "expiry_year": now.year + 1,
            "expiry_month": now.month,
            "daily_limit": "10000.00",
            "last_four": "1234",
            "transactions": [],
        }]
        self.account["failed_attempts"] = bank_service.MAX_PIN_ATTEMPTS - 1

        with patch.object(bank_service, "verify_pin", return_value=False):
            response = self.client.post(
                "/api/cards/CARD-TEST/payment",
                json={
                    "merchant": "Test merchant",
                    "amount": "1.00",
                    "pin": "0000",
                },
            )

        self.assertEqual(response.status_code, 423)
        self.assertGreater(self.account["locked_until"], time.time())
        self.assertEqual(self.account["failed_attempts"], 0)
        self.assertEqual(self.account["balance"], Decimal("100.00"))
        self.assertEqual(self.account["transactions"], [])
        self.assertEqual(len(self.account["notifications"]), 1)

    def test_transfer_pin_failures_share_the_account_lockout(self):
        self.account["failed_attempts"] = bank_service.MAX_PIN_ATTEMPTS - 1
        with patch.object(bank_service, "verify_pin", return_value=False):
            response = self.client.post(
                "/api/transfer",
                json={
                    "beneficiary_id": "BEN-TEST",
                    "amount": "10.00",
                    "pin": "4826",
                },
            )

        self.assertEqual(response.status_code, 423)
        self.assertGreater(self.account["locked_until"], time.time())
        self.assertEqual(self.account["balance"], Decimal("100.00"))
        self.assertEqual(self.recipient["balance"], Decimal("0.00"))
        self.assertEqual(self.account["transactions"], [])

    def test_change_pin_wrong_current_pin_records_a_failed_attempt(self):
        with patch.object(bank_service, "verify_pin", return_value=False):
            response = self.client.post(
                "/api/change-pin",
                json={"current_pin": "0000", "new_pin": "4826"},
            )

        self.assertEqual(response.status_code, 401)
        self.assertEqual(self.account["failed_attempts"], 1)
        self.assertEqual(self.account["locked_until"], 0)
        self.save_data_mock.assert_called_once()

    def test_failed_pin_attempt_rolls_back_when_security_state_cannot_be_saved(self):
        with (
            patch.object(bank_service, "verify_pin", return_value=False),
            patch.object(bank_service, "save_data", return_value=False),
        ):
            response = self.client.post(
                "/api/change-pin",
                json={"current_pin": "0000", "new_pin": "4826"},
            )

        self.assertEqual(response.status_code, 503)
        self.assertEqual(self.account["failed_attempts"], 0)
        self.assertEqual(self.account["locked_until"], 0)
        self.assertEqual(self.account["notifications"], [])

    def test_locked_account_cannot_schedule_a_transfer(self):
        self.account["locked_until"] = time.time() + 60
        scheduled_for = (datetime.now(timezone.utc) + timedelta(days=2)).isoformat()
        with (
            patch.object(bank_service, "verify_pin") as verify_pin,
            patch.object(
                bank_service.scheduled_transfers_collection,
                "insert_one",
            ) as insert_schedule,
        ):
            response = self.client.post(
                "/api/scheduled-transfers",
                json={
                    "beneficiary_id": "BEN-TEST",
                    "amount": "25.00",
                    "scheduled_for": scheduled_for,
                    "frequency": "ONCE",
                    "pin": "4826",
                },
            )

        self.assertEqual(response.status_code, 423)
        verify_pin.assert_not_called()
        insert_schedule.assert_not_called()
        self.save_data_mock.assert_not_called()

    def test_scheduled_transfer_rejects_malformed_identifiers_and_dates(self):
        valid_payload = {
            "beneficiary_id": "BEN-TEST",
            "amount": "25.00",
            "scheduled_for": (
                datetime.now(timezone.utc) + timedelta(days=2)
            ).isoformat(),
            "frequency": "ONCE",
            "pin": "4826",
        }
        malformed_payloads = []
        for field, value in (
            ("beneficiary_id", ["BEN-TEST"]),
            ("frequency", ["ONCE"]),
            ("scheduled_for", 20261120),
        ):
            payload = dict(valid_payload)
            payload[field] = value
            malformed_payloads.append(payload)

        for payload in malformed_payloads:
            with self.subTest(payload=payload):
                response = self.client.post("/api/scheduled-transfers", json=payload)
                self.assertEqual(response.status_code, 400)

        self.assertEqual(self.account["transactions"], [])
        self.save_data_mock.assert_not_called()

    def test_dispute_submission_rejects_non_text_fields(self):
        self.account["transactions"] = [{
            "id": "TX-DISPUTE",
            "type": "CARD_PAYMENT",
            "amount": "12.50",
            "status": "COMPLETED",
        }]

        with patch.object(
            bank_service.disputes_collection,
            "find_one",
        ) as find_dispute:
            invalid_issue = self.client.post(
                "/api/transactions/TX-DISPUTE/dispute",
                json={"issue": ["OTHER"], "notes": ""},
            )
            invalid_notes = self.client.post(
                "/api/transactions/TX-DISPUTE/dispute",
                json={"issue": "OTHER", "notes": ["not text"]},
            )

        self.assertEqual(invalid_issue.status_code, 400)
        self.assertEqual(invalid_notes.status_code, 400)
        find_dispute.assert_not_called()
        self.assertNotIn("dispute_id", self.account["transactions"][0])

    def test_scheduled_transfer_is_pending_until_worker_runs(self):
        inserted = []
        with (
            patch.object(
                bank_service.mongo_client,
                "start_session",
                return_value=NoopMongoTransaction(),
            ),
            patch.object(bank_service, "save_accounts_atomic") as save_atomic,
            patch.object(bank_service, "mark_accounts_persisted"),
            patch.object(
                bank_service.scheduled_transfers_collection,
                "insert_one",
                side_effect=lambda document, **kwargs: inserted.append(document),
            ),
        ):
            response = self.client.post(
                "/api/scheduled-transfers",
                json={
                    "beneficiary_id": "BEN-TEST",
                    "amount": "25.00",
                    "scheduled_for": (
                        datetime.now(timezone.utc) + timedelta(days=2)
                    ).isoformat(),
                    "frequency": "ONCE",
                    "pin": "4826",
                },
            )

        self.assertEqual(response.status_code, 201)
        self.assertEqual(inserted[0]["status"], "ACTIVE")
        self.assertEqual(inserted[0]["frequency"], "ONCE")
        self.assertEqual(self.account["transactions"][0]["status"], "PENDING")
        save_atomic.assert_called_once()

    def test_worker_completes_due_transfer_and_updates_both_histories(self):
        transaction = {
            "id": "TXN-SCHEDULED",
            "type": "SCHEDULED_TRANSFER",
            "schedule_id": "SCH-TEST",
            "amount": "25.00",
            "status": "PENDING",
        }
        self.account["transactions"] = [transaction]
        schedule = {
            "id": "SCH-TEST",
            "account_number": ACCOUNT_NUMBER,
            "recipient_account": RECIPIENT_NUMBER,
            "recipient_name": "Recipient User",
            "amount": "25.00",
            "frequency": "ONCE",
            "status": "ACTIVE",
            "transaction_id": "TXN-SCHEDULED",
            "next_run_at": datetime.now(timezone.utc).isoformat(),
        }
        with (
            patch.object(
                bank_service,
                "refresh_account",
                side_effect={
                    ACCOUNT_NUMBER: self.account,
                    RECIPIENT_NUMBER: self.recipient,
                }.get,
            ),
            patch.object(
                bank_service.mongo_client,
                "start_session",
                return_value=NoopMongoTransaction(),
            ),
            patch.object(bank_service, "save_accounts_atomic") as save_atomic,
            patch.object(bank_service, "mark_accounts_persisted"),
            patch.object(
                bank_service.scheduled_transfers_collection,
                "update_one",
                return_value=SimpleNamespace(matched_count=1),
            ) as update_schedule,
        ):
            _process_claimed_scheduled_transfer(
                schedule,
                "claim-token",
                datetime.now(timezone.utc),
            )

        self.assertEqual(self.account["balance"], Decimal("75.00"))
        self.assertEqual(self.recipient["balance"], Decimal("25.00"))
        self.assertEqual(transaction["status"], "COMPLETED")
        self.assertEqual(self.recipient["transactions"][0]["status"], "COMPLETED")
        save_atomic.assert_called_once()
        self.assertIn("session", update_schedule.call_args.kwargs)

    def test_large_transaction_setting_applies_to_transfers(self):
        self.account["alert_preferences"] = {
            **bank_service.default_alert_preferences(),
            "transaction_alerts_enabled": False,
            "large_transaction_threshold": "10.00",
        }

        app_module.create_transaction_alerts(
            self.account,
            {"type": "TRANSFER", "amount": "25.00"},
            Decimal("100.00"),
        )

        self.assertFalse(
            any(
                item["title"] == "Large transaction"
                for item in self.account["notifications"]
            )
        )

    def test_transfer_setting_does_not_disable_large_transaction_alerts(self):
        self.account["alert_preferences"] = {
            **bank_service.default_alert_preferences(),
            "transfer_alerts_enabled": False,
            "large_transaction_threshold": "10.00",
        }

        app_module.create_transaction_alerts(
            self.account,
            {"type": "TRANSFER", "amount": "25.00"},
            Decimal("100.00"),
        )

        self.assertEqual(
            self.account["notifications"][0]["title"],
            "Large transaction",
        )

    def test_transfer_setting_suppresses_transfer_notifications(self):
        disabled_preferences = {
            **bank_service.default_alert_preferences(),
            "transfer_alerts_enabled": False,
        }
        self.account["alert_preferences"] = disabled_preferences
        self.recipient["alert_preferences"] = disabled_preferences

        with patch.object(bank_service, "save_accounts_atomic"):
            response = self.client.post(
                "/api/transfer",
                json={
                    "beneficiary_id": "BEN-TEST",
                    "amount": "25.00",
                    "pin": "4826",
                },
            )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(self.account["notifications"], [])
        self.assertEqual(self.recipient["notifications"], [])

    def test_alert_preferences_endpoint_persists_disabled_toggles(self):
        response = self.client.put(
            "/api/alerts",
            json={
                "transaction_alerts_enabled": False,
                "transfer_alerts_enabled": False,
            },
        )

        self.assertEqual(response.status_code, 200)
        self.assertFalse(
            self.account["alert_preferences"]["transaction_alerts_enabled"]
        )
        self.assertFalse(
            self.account["alert_preferences"]["transfer_alerts_enabled"]
        )
        self.save_data_mock.assert_called_once()

    def test_development_reloader_starts_only_one_transfer_worker(self):
        with patch.dict(os.environ, {"WERKZEUG_RUN_MAIN": "false"}):
            self.assertIsNone(app_module.start_scheduled_transfer_worker())

        with (
            patch.dict(os.environ, {"WERKZEUG_RUN_MAIN": "true"}),
            patch.object(app_module.subprocess, "Popen") as start_process,
        ):
            worker = app_module.start_scheduled_transfer_worker()

        self.assertIs(worker, start_process.return_value)
        command = start_process.call_args.args[0]
        self.assertEqual(command[0], app_module.sys.executable)
        self.assertEqual(os.path.basename(command[1]), "scheduled_transfer_worker.py")

    def test_spending_insights_exclude_failed_and_pending_transactions(self):
        created_at = datetime.now(timezone.utc).isoformat()
        self.account["transactions"] = [
            {
                "id": "TX-1",
                "type": "CARD_PAYMENT",
                "amount": "20.00",
                "category": "Food",
                "status": "COMPLETED",
                "created_at": created_at,
            },
            {
                "id": "TX-2",
                "type": "CARD_PAYMENT",
                "amount": "99.00",
                "category": "Food",
                "status": "FAILED",
                "created_at": created_at,
            },
        ]
        response = self.client.get("/api/insights")

        self.assertEqual(response.status_code, 200)
        payload = response.get_json()
        self.assertEqual(payload["total_spending"], "20.00")
        self.assertEqual(payload["categories"], [{"category": "Food", "spent": "20.00"}])


class DataChangeAuthorizationTests(unittest.TestCase):
    def setUp(self):
        self.client = flask_app.test_client()

    def test_customer_mutations_require_an_authenticated_account(self):
        requests = [
            ("post", "/api/cards/card-1/payment", {}),
            ("post", "/api/cards", {}),
            ("patch", "/api/cards/card-1/freeze", {}),
            ("patch", "/api/cards/card-1/unfreeze", {}),
            ("patch", "/api/cards/card-1/limit", {}),
            ("patch", "/api/cards/card-1/activate", {}),
            ("patch", "/api/cards/card-1/block", {}),
            ("post", "/api/cards/card-1/replace", {}),
            ("post", "/api/cards/virtual", {}),
            ("put", "/api/profile", {}),
            ("post", "/api/deposit", {}),
            ("post", "/api/withdraw", {}),
            ("patch", "/api/transactions/tx-1/category", {}),
            ("post", "/api/change-pin", {}),
            ("post", "/api/beneficiaries", {}),
            ("put", "/api/beneficiaries/beneficiary-1", {}),
            ("delete", "/api/beneficiaries/beneficiary-1", None),
            ("post", "/api/transfer", {}),
            ("post", "/api/scheduled-transfers", {}),
            ("delete", "/api/scheduled-transfers/schedule-1", None),
            ("patch", "/api/notifications/notification-1/read", {}),
            ("patch", "/api/notifications/read-all", {}),
            ("put", "/api/alerts", {}),
            ("delete", "/api/sessions/session-1", None),
            ("put", "/api/budgets/Food", {}),
            ("delete", "/api/budgets/Food", None),
            ("post", "/api/savings-goals", {}),
            ("post", "/api/savings-goals/goal-1/contribute", {}),
            ("post", "/api/savings-goals/goal-1/withdraw", {}),
            ("post", "/api/transactions/tx-1/dispute", {}),
            ("post", "/api/2fa/setup", {}),
            ("post", "/api/2fa/verify-setup", {}),
            ("post", "/api/2fa/disable", {}),
        ]

        for method, path, payload in requests:
            with self.subTest(method=method, path=path):
                request_method = getattr(self.client, method)
                response = (
                    request_method(path)
                    if payload is None
                    else request_method(path, json=payload)
                )
                self.assertEqual(response.status_code, 401)

    def test_staff_mutations_require_an_authorized_staff_session(self):
        requests = [
            ("post", "/api/staff/accounts/account-ref/flags", {}),
            ("patch", "/api/staff/accounts/account-ref/flags/flag-1", {}),
            ("patch", "/api/staff/disputes/dispute-1", {}),
        ]

        for method, path, payload in requests:
            with self.subTest(method=method, path=path):
                response = getattr(self.client, method)(path, json=payload)
                self.assertEqual(response.status_code, 403)


class MongoPersistenceTests(unittest.TestCase):
    def test_login_refreshes_mongo_before_checking_a_recent_pin_change(self):
        stored_salt, stored_hash = bank_service.hash_pin("4826")
        stale_salt, stale_hash = bank_service.hash_pin("1357")
        stale_account = {
            "name": "Test User",
            "age": 22,
            "account_number": ACCOUNT_NUMBER,
            "balance": Decimal("100.00"),
            "transactions": [],
            "pin_salt": stale_salt,
            "pin_hash": stale_hash,
            "failed_attempts": 0,
            "locked_until": 0,
        }
        persisted_account = {
            **stale_account,
            "pin_salt": stored_salt,
            "pin_hash": stored_hash,
        }
        client = flask_app.test_client()

        with (
            patch.dict(
                bank_service.accounts,
                {ACCOUNT_NUMBER: stale_account},
                clear=True,
            ),
            patch.object(
                bank_service,
                "refresh_account",
                return_value=persisted_account,
            ) as refresh_account,
            patch.object(bank_service, "save_data", return_value=True),
            patch(
                "app.register_server_session",
                return_value="server-session",
            ),
        ):
            response = client.post(
                "/api/login",
                json={
                    "account_number": ACCOUNT_NUMBER,
                    "pin": "4826",
                },
            )

        self.assertEqual(response.status_code, 200)
        refresh_account.assert_called_once_with(ACCOUNT_NUMBER)

    def test_account_save_uses_version_guard_and_writes_only_changed_record(self):
        account = {
            "account_number": ACCOUNT_NUMBER,
            "name": "Test User",
            "balance": Decimal("90.00"),
            "transactions": [],
        }
        snapshot = bank_service._serialize_account(ACCOUNT_NUMBER, account)
        snapshot["balance"] = "100.00"

        class FakeCollection:
            def __init__(self):
                self.query = None
                self.document = None

            def update_one(self, query, update, **kwargs):
                self.query = query
                self.document = update["$set"]
                return SimpleNamespace(matched_count=1, upserted_id=None)

        collection = FakeCollection()
        with (
            patch.object(bank_service, "accounts", {ACCOUNT_NUMBER: account}),
            patch.object(bank_service, "_persisted_snapshots", {
                ACCOUNT_NUMBER: copy.deepcopy(snapshot),
            }),
            patch.object(bank_service, "_account_versions", {ACCOUNT_NUMBER: 4}),
            patch.object(bank_service, "accounts_collection", collection),
        ):
            self.assertTrue(bank_service.save_data())

        self.assertEqual(collection.query["_version"], 4)
        self.assertEqual(collection.document["_version"], 5)
        self.assertEqual(collection.document["balance"], "90.00")

    def test_account_save_rejects_a_stale_version(self):
        account = {
            "account_number": ACCOUNT_NUMBER,
            "name": "Test User",
            "balance": Decimal("90.00"),
            "transactions": [],
        }
        snapshot = bank_service._serialize_account(ACCOUNT_NUMBER, account)
        snapshot["balance"] = "100.00"

        class FakeCollection:
            def update_one(self, query, update, **kwargs):
                return SimpleNamespace(matched_count=0, upserted_id=None)

        with (
            patch.object(bank_service, "accounts", {ACCOUNT_NUMBER: account}),
            patch.object(bank_service, "_persisted_snapshots", {
                ACCOUNT_NUMBER: snapshot,
            }),
            patch.object(bank_service, "_account_versions", {ACCOUNT_NUMBER: 4}),
            patch.object(bank_service, "accounts_collection", FakeCollection()),
        ):
            self.assertFalse(bank_service.save_data())

    def test_recurring_monthly_schedule_keeps_end_of_month_anchor(self):
        now = datetime(2026, 3, 1, tzinfo=timezone.utc)

        result = _next_schedule_occurrence(
            "2026-02-28T09:00:00+00:00",
            "MONTHLY",
            now,
            day_of_month=31,
        )

        self.assertEqual(result.isoformat(), "2026-03-31T09:00:00+00:00")


class StaffAdminEndpointTests(unittest.TestCase):
    def setUp(self):
        self.account_record = {
            "account_number": ACCOUNT_NUMBER,
            "name": "Test User",
            "email": "test.user@example.com",
            "balance": "125.00",
            "locked_until": 0,
            "transactions": [
                {
                    "id": "TX-STAFF-1",
                    "type": "TRANSFER",
                    "amount": "25.00",
                    "status": "COMPLETED",
                    "reference": "REF-1",
                    "created_at": "2026-10-12T10:30:00+00:00",
                },
                {
                    "id": "TX-STAFF-2",
                    "type": "WITHDRAW",
                    "amount": "10.00",
                    "status": "FAILED",
                    "created_at": "2026-10-13T10:30:00+00:00",
                },
            ],
        }
        self.client = flask_app.test_client()
        with self.client.session_transaction() as browser_session:
            browser_session["session_role"] = "staff"
            browser_session["staff_username"] = "support.alex"
            browser_session["staff_role"] = "admin"
            browser_session["server_session_id"] = "staff-session"
            browser_session["login_time"] = time.time()
            browser_session["last_activity"] = time.time()

        self.patchers = [
            patch(
                "app.active_session_record",
                return_value={"role": "staff", "account_number": None},
            ),
            patch.object(
                bank_service.sessions_collection,
                "update_one",
                return_value=SimpleNamespace(matched_count=1),
            ),
            patch.object(
                bank_service.accounts_collection,
                "find",
                return_value=[self.account_record],
            ),
            patch.object(
                app_module.staff_account_flags,
                "find",
                return_value=[],
            ),
            patch.object(
                app_module.staff_account_flags,
                "find_one",
                return_value=None,
            ),
            patch.object(
                bank_service.audit_log_collection,
                "insert_one",
            ),
        ]
        for patcher in self.patchers:
            patcher.start()

    def tearDown(self):
        for patcher in reversed(self.patchers):
            patcher.stop()

    def test_customer_lookup_returns_masked_profile_and_recent_activity(self):
        response = self.client.get("/api/staff/customers?q=Test")

        self.assertEqual(response.status_code, 200)
        payload = response.get_json()
        customer = payload["customers"][0]
        self.assertEqual(customer["account_number_masked"], "•••• 3507")
        self.assertEqual(customer["email_masked"], "t***@example.com")
        self.assertNotIn(ACCOUNT_NUMBER, response.get_data(as_text=True))
        self.assertEqual(len(customer["recent_transactions"]), 2)

    def test_transaction_search_filters_and_paginates_results(self):
        response = self.client.get(
            "/api/staff/transactions",
            query_string={
                "type": "TRANSFER",
                "min_amount": "20",
                "page_size": "1",
            },
        )

        self.assertEqual(response.status_code, 200)
        payload = response.get_json()
        self.assertEqual(payload["pagination"]["total"], 1)
        self.assertEqual(payload["transactions"][0]["id"], "TX-STAFF-1")
        self.assertEqual(
            payload["transactions"][0]["account_number_masked"],
            "•••• 3507",
        )

    def test_read_only_staff_cannot_create_account_flags(self):
        with self.client.session_transaction() as browser_session:
            browser_session["staff_role"] = "read_only"

        response = self.client.post(
            "/api/staff/accounts/invalid/flags",
            json={"reason": "Needs review"},
        )

        self.assertEqual(response.status_code, 403)

    def test_flag_creation_requires_reason(self):
        account_ref = app_module._staff_account_ref(ACCOUNT_NUMBER)

        response = self.client.post(
            f"/api/staff/accounts/{account_ref}/flags",
            json={"reason": "   "},
        )

        self.assertEqual(response.status_code, 400)

    def test_flag_creation_is_audited_and_does_not_expose_account_number(self):
        account_ref = app_module._staff_account_ref(ACCOUNT_NUMBER)
        with (
            patch.object(
                bank_service.mongo_client,
                "start_session",
                return_value=NoopMongoTransaction(),
            ),
            patch.object(app_module.staff_account_flags, "insert_one") as insert_flag,
        ):
            response = self.client.post(
                f"/api/staff/accounts/{account_ref}/flags",
                json={"reason": "Customer requested follow-up"},
            )

        self.assertEqual(response.status_code, 201)
        self.assertNotIn(ACCOUNT_NUMBER, response.get_data(as_text=True))
        self.assertEqual(
            insert_flag.call_args.args[0]["created_by"],
            "support.alex",
        )
        self.assertIn("session", insert_flag.call_args.kwargs)

    def test_dispute_resolution_response_excludes_mongo_id(self):
        dispute = {
            "_id": object(),
            "id": "DSP-TEST",
            "account_number": ACCOUNT_NUMBER,
            "transaction_id": "TX-DISPUTE",
            "transaction_type": "CARD_PAYMENT",
            "amount": "12.50",
            "issue": "OTHER",
            "status": "OPEN",
            "history": [],
        }

        def find_dispute(query, projection):
            return {
                key: value
                for key, value in dispute.items()
                if projection.get(key, 1) != 0
            }

        with (
            patch.object(
                bank_service.disputes_collection,
                "find_one",
                side_effect=find_dispute,
            ) as find_one,
            patch.object(
                bank_service.disputes_collection,
                "update_one",
                return_value=SimpleNamespace(matched_count=1),
            ),
            patch.object(
                bank_service.mongo_client,
                "start_session",
                return_value=NoopMongoTransaction(),
            ),
        ):
            response = self.client.patch(
                "/api/staff/disputes/DSP-TEST",
                json={"action": "RESOLVED", "resolution": "Reviewed"},
            )

        self.assertEqual(response.status_code, 200)
        self.assertNotIn("_id", response.get_json()["dispute"])
        self.assertNotIn(ACCOUNT_NUMBER, response.get_data(as_text=True))
        self.assertEqual(
            response.get_json()["dispute"]["account_number_masked"],
            "•••• 3507",
        )
        self.assertEqual(
            find_one.call_args.args[1],
            {"_id": 0},
        )

    def test_dispute_closure_requires_text_resolution_notes(self):
        with patch.object(
            bank_service.disputes_collection,
            "find_one",
        ) as find_dispute:
            responses = [
                self.client.patch(
                    "/api/staff/disputes/DSP-TEST",
                    json={"action": "RESOLVED"},
                ),
                self.client.patch(
                    "/api/staff/disputes/DSP-TEST",
                    json={"action": "DECLINED", "resolution": "   "},
                ),
                self.client.patch(
                    "/api/staff/disputes/DSP-TEST",
                    json={"action": ["RESOLVED"], "resolution": "Reviewed"},
                ),
                self.client.patch(
                    "/api/staff/disputes/DSP-TEST",
                    json={"action": "RESOLVED", "resolution": []},
                ),
            ]

        self.assertEqual([response.status_code for response in responses], [400] * 4)
        find_dispute.assert_not_called()

    def test_dashboard_summarizes_open_disputes_and_active_flags(self):
        recent = datetime.now(timezone.utc).isoformat()
        with (
            patch.object(
                bank_service.disputes_collection,
                "find",
                return_value=[
                    {"status": "OPEN", "created_at": recent},
                    {"status": "UNDER_REVIEW", "created_at": recent},
                ],
            ),
            patch.object(
                app_module.staff_account_flags,
                "find",
                return_value=[
                    {
                        "id": "FLG-1",
                        "account_number": ACCOUNT_NUMBER,
                        "reason": "Follow-up",
                        "status": "ACTIVE",
                        "created_at": recent,
                    },
                    {
                        "id": "FLG-2",
                        "account_number": RECIPIENT_NUMBER,
                        "reason": "Resolved",
                        "status": "RESOLVED",
                        "created_at": recent,
                    },
                ],
            ),
        ):
            response = self.client.get("/api/staff/dashboard")

        self.assertEqual(response.status_code, 200)
        summary = response.get_json()["summary"]
        self.assertEqual(summary["open_disputes"], 1)
        self.assertEqual(summary["under_review_disputes"], 1)
        self.assertEqual(summary["active_account_flags"], 1)
        self.assertEqual(summary["pending_staff_work"], 3)

    def test_staff_user_configuration_assigns_named_roles(self):
        with patch.dict(
            os.environ,
            {
                "BANK_STAFF_USERS": (
                    '[{"username":"support.alex","password_hash":"hash",'
                    '"role":"support"}]'
                ),
                "BANK_STAFF_USERNAME": "",
                "BANK_STAFF_PASSWORD_HASH": "",
            },
        ):
            users = configured_staff_users()

        self.assertEqual(users["support.alex"]["role"], "support")

    def test_admin_can_create_staff_account_with_hashed_password(self):
        created = {}

        def insert_staff_user(document, **kwargs):
            created.update(document)

        with (
            patch.object(app_module, "require_staff", return_value=True),
            patch.dict(
                os.environ,
                {
                    "BANK_STAFF_USERS": "",
                    "BANK_STAFF_USERNAME": "",
                    "BANK_STAFF_PASSWORD_HASH": "",
                },
            ),
            patch.object(app_module, "staff_users_collection") as staff_users,
            patch.object(
                bank_service.mongo_client,
                "start_session",
                return_value=NoopMongoTransaction(),
            ),
            patch.object(app_module, "_append_audit_entry") as audit_entry,
        ):
            staff_users.find_one.return_value = None
            staff_users.insert_one.side_effect = insert_staff_user

            response = self.client.post(
                "/api/staff/users",
                json={
                    "username": "review.jamie",
                    "password": "a-strong-password",
                    "role": "reviewer",
                },
            )

        self.assertEqual(response.status_code, 201)
        self.assertEqual(created["username"], "review.jamie")
        self.assertEqual(created["username_key"], "review.jamie")
        self.assertTrue(check_password_hash(
            created["password_hash"],
            "a-strong-password",
        ))
        self.assertNotIn("password_hash", response.get_json()["staff_user"])
        self.assertNotIn("a-strong-password", response.get_data(as_text=True))
        audit_entry.assert_called_once()

    def test_staff_user_creation_requires_admin_permission(self):
        with patch.object(app_module, "require_staff", return_value=False):
            response = self.client.post(
                "/api/staff/users",
                json={
                    "username": "support.jordan",
                    "password": "a-strong-password",
                    "role": "support",
                },
            )

        self.assertEqual(response.status_code, 403)

    def test_staff_user_creation_rejects_short_passwords(self):
        with patch.object(app_module, "require_staff", return_value=True):
            response = self.client.post(
                "/api/staff/users",
                json={
                    "username": "support.jordan",
                    "password": "short",
                    "role": "support",
                },
            )

        self.assertEqual(response.status_code, 400)
        self.assertIn("12 and 128", response.get_json()["message"])

    def test_managed_staff_user_can_sign_in_with_assigned_role(self):
        password_hash = generate_password_hash("a-strong-password")
        managed_user = {
            "id": "STF-TEST",
            "username": "review.jamie",
            "password_hash": password_hash,
            "role": "reviewer",
        }
        with (
            patch.dict(
                flask_app.config,
                {"SECRET_KEY": "test-secret"},
            ),
            patch(
                "app.configured_staff_users",
                return_value={},
            ),
            patch.object(
                app_module.staff_users_collection,
                "find_one",
                return_value=managed_user,
            ),
            patch(
                "app.register_server_session",
                return_value="staff-session",
            ),
        ):
            response = self.client.post(
                "/api/staff/login",
                json={
                    "username": "REVIEW.JAMIE",
                    "password": "a-strong-password",
                },
            )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(
            response.get_json()["staff"],
            {"username": "review.jamie", "role": "reviewer"},
        )

    def test_staff_directory_never_returns_password_hashes(self):
        with (
            patch.object(app_module, "require_staff", return_value=True),
            patch.dict(
                os.environ,
                {
                    "BANK_STAFF_USERS": "",
                    "BANK_STAFF_USERNAME": "",
                    "BANK_STAFF_PASSWORD_HASH": "",
                },
            ),
            patch.object(app_module, "staff_users_collection") as staff_users,
            patch.object(app_module, "_record_staff_access", return_value=True),
        ):
            staff_users.find.return_value = [{
                "id": "STF-TEST",
                "username": "support.jordan",
                "username_key": "support.jordan",
                "password_hash": "secret-hash",
                "role": "support",
                "active": True,
            }]

            response = self.client.get("/api/staff/users")

        self.assertEqual(response.status_code, 200)
        result = response.get_json()["staff_users"]
        self.assertEqual(result[0]["username"], "support.jordan")
        self.assertEqual(result[0]["role"], "support")
        self.assertNotIn("password_hash", result[0])

    def test_staff_password_reset_stores_only_a_hash_and_ends_sessions(self):
        staff_user = {
            "id": "STF-TEST",
            "username": "support.jordan",
            "role": "support",
            "source": "managed",
            "active": True,
        }
        with (
            patch.object(app_module, "require_staff", return_value=True),
            patch.object(app_module, "_staff_account_by_id", return_value=staff_user),
            patch.object(app_module, "_update_staff_account", return_value=True) as update,
        ):
            response = self.client.post(
                "/api/staff/users/STF-TEST/password",
                json={"password": "a-new-strong-password"},
            )

        self.assertEqual(response.status_code, 200)
        self.assertNotIn("a-new-strong-password", response.get_data(as_text=True))
        update_args = update.call_args.args
        self.assertTrue(check_password_hash(
            update_args[1]["password_hash"],
            "a-new-strong-password",
        ))
        self.assertNotEqual(update_args[1]["password_hash"], "a-new-strong-password")
        self.assertEqual(update_args[2], "STAFF_PASSWORD_RESET")
        self.assertNotIn("password", update_args[3])

    def test_staff_password_reset_revokes_matching_server_sessions(self):
        staff_user = {
            "id": "STF-TEST",
            "username": "support.jordan",
            "role": "support",
            "source": "managed",
        }
        with (
            patch.object(app_module.staff_users_collection, "update_one") as update_user,
            patch.object(bank_service.sessions_collection, "update_many") as update_sessions,
            patch.object(bank_service.mongo_client, "start_session", return_value=NoopMongoTransaction()),
            patch.object(app_module, "_append_audit_entry") as audit_entry,
        ):
            update_user.return_value = SimpleNamespace(matched_count=1)
            result = app_module._update_staff_account(
                staff_user,
                {"password_hash": "hashed-value", "password_changed_at": "2026-03-01T00:00:00+00:00"},
                "STAFF_PASSWORD_RESET",
                {"username": "support.jordan", "role": "support"},
            )

        self.assertTrue(result)
        update_sessions.assert_called_once()
        self.assertEqual(
            update_sessions.call_args.args[0]["staff_username_key"],
            "support.jordan",
        )
        self.assertTrue(update_sessions.call_args.args[1]["$set"]["revoked"])
        audit_entry.assert_called_once()

    def test_staff_admin_cannot_revoke_self_or_last_active_admin(self):
        self_user = {
            "id": "STF-SELF",
            "username": "admin.alex",
            "role": "admin",
            "source": "managed",
            "active": True,
        }
        last_admin = {
            **self_user,
            "id": "STF-LAST",
            "username": "admin.jamie",
        }
        with self.client.session_transaction() as browser_session:
            browser_session["staff_username"] = "admin.alex"
        with (
            patch.object(app_module, "require_staff", return_value=True),
            patch.object(app_module, "_update_staff_account") as update,
        ):
            with (
                patch.object(app_module, "_staff_account_by_id", return_value=self_user),
                patch.object(app_module, "staff_directory_records", return_value=[self_user]),
            ):
                self_revoke = self.client.post("/api/staff/users/STF-SELF/revoke")
            with (
                patch.object(app_module, "_staff_account_by_id", return_value=last_admin),
                patch.object(app_module, "staff_directory_records", return_value=[last_admin]),
            ):
                last_admin_revoke = self.client.post("/api/staff/users/STF-LAST/revoke")

        self.assertEqual(self_revoke.status_code, 409)
        self.assertIn("your own", self_revoke.get_json()["message"])
        self.assertEqual(last_admin_revoke.status_code, 409)
        self.assertIn("last active admin", last_admin_revoke.get_json()["message"])
        update.assert_not_called()

    def test_environment_staff_password_override_is_used_for_login(self):
        old_hash = generate_password_hash("the-original-password")
        reset_hash = generate_password_hash("the-reset-password")
        configured_user = {
            "username": "admin.alex",
            "password_hash": old_hash,
            "role": "admin",
        }
        with (
            patch.dict(
                flask_app.config,
                {"SECRET_KEY": "test-secret"},
            ),
            patch(
                "app.configured_staff_users",
                return_value={"admin.alex": configured_user},
            ),
            patch.object(
                app_module.staff_users_collection,
                "find_one",
                return_value={
                    "id": "ENV-admin.alex",
                    "username": "admin.alex",
                    "password_hash": reset_hash,
                    "role": "admin",
                    "source": "environment",
                    "active": True,
                },
            ),
            patch(
                "app.register_server_session",
                return_value="staff-session",
            ) as register_session,
        ):
            response = self.client.post(
                "/api/staff/login",
                json={
                    "username": "ADMIN.ALEX",
                    "password": "the-reset-password",
                },
            )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.get_json()["staff"]["role"], "admin")
        register_session.assert_called_once_with(
            "staff",
            staff_username="admin.alex",
        )

    def test_revoked_environment_staff_account_cannot_sign_in(self):
        configured_user = {
            "username": "admin.alex",
            "password_hash": generate_password_hash("the-original-password"),
            "role": "admin",
        }
        with (
            patch.dict(
                flask_app.config,
                {"SECRET_KEY": "test-secret"},
            ),
            patch(
                "app.configured_staff_users",
                return_value={"admin.alex": configured_user},
            ),
            patch.object(
                app_module.staff_users_collection,
                "find_one",
                return_value={
                    "id": "ENV-admin.alex",
                    "username": "admin.alex",
                    "password_hash": configured_user["password_hash"],
                    "role": "admin",
                    "source": "environment",
                    "active": False,
                },
            ),
            patch("app.register_server_session") as register_session,
        ):
            response = self.client.post(
                "/api/staff/login",
                json={
                    "username": "admin.alex",
                    "password": "the-original-password",
                },
            )

        self.assertEqual(response.status_code, 401)
        register_session.assert_not_called()

    def test_reactivated_account_rejects_sessions_created_before_revocation(self):
        with self.client.session_transaction() as browser_session:
            browser_session.pop("account_number", None)
            browser_session["session_role"] = "staff"
            browser_session["staff_username"] = "support.jordan"
            browser_session["staff_role"] = "support"
            browser_session["server_session_id"] = "old-session"
        with (
            patch(
                "app.active_session_record",
                return_value={
                    "role": "staff",
                    "account_number": None,
                    "created_at": "2026-03-01T10:00:00+00:00",
                },
            ),
            patch.object(
                app_module.staff_users_collection,
                "find_one",
                return_value={
                    "active": True,
                    "access_revoked_at": "2026-03-01T11:00:00+00:00",
                },
            ),
            patch.object(bank_service.sessions_collection, "update_one"),
        ):
            response = self.client.get("/api/staff/me")

        self.assertEqual(response.status_code, 403)

    def test_staff_account_database_error_returns_service_unavailable(self):
        with self.client.session_transaction() as browser_session:
            browser_session.pop("account_number", None)
            browser_session["session_role"] = "staff"
            browser_session["staff_username"] = "support.jordan"
            browser_session["staff_role"] = "support"
            browser_session["server_session_id"] = "staff-session"
        with (
            patch(
                "app.active_session_record",
                return_value={"role": "staff", "account_number": None},
            ),
            patch.object(bank_service.sessions_collection, "update_one"),
            patch.object(
                app_module.staff_users_collection,
                "find_one",
                side_effect=AutoReconnect("MongoDB unavailable"),
            ),
        ):
            response = self.client.get("/api/staff/me")

        self.assertEqual(response.status_code, 503)
        self.assertIn("temporarily unavailable", response.get_json()["message"])


if __name__ == "__main__":
    unittest.main()
