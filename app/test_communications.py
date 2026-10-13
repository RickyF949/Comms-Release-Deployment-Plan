import reflex as rx

import unittest
import io
import logging
from datetime import date, datetime, timezone
from unittest.mock import patch

from starlette.applications import Starlette
from starlette.routing import Route
from starlette.testclient import TestClient

from app.communication_validation import DATE_PATTERN, PHONE_PATTERN
from app.communications_webhook import communications_webhook
from app.secure_logging import log_failure, redact
from app.models import PendingComm, CommunicationLog
from app.release_worker import local_eligible, run_once


class CommunicationsSafetyTests(unittest.TestCase):
    def test_e164_validation(self):
        self.assertIsNotNone(PHONE_PATTERN.fullmatch("+61412345678"))
        for invalid in (
            "0412345678",
            "+01234",
            "+61 412345678",
            "+1234567890123456",
            "+61\n",
        ):
            self.assertIsNone(PHONE_PATTERN.fullmatch(invalid))

    def test_iso_date_shape(self):
        self.assertIsNotNone(DATE_PATTERN.fullmatch("2026-01-05"))
        self.assertIsNone(DATE_PATTERN.fullmatch("20260105"))
        self.assertIsNone(DATE_PATTERN.fullmatch("2026-1-5"))

    def test_business_hour_boundaries(self):
        delivery = date(2026, 1, 5)
        for hour, minute, expected in (
            (8, 59, False),
            (9, 0, True),
            (16, 59, True),
            (17, 0, False),
        ):
            self.assertEqual(
                local_eligible(
                    delivery,
                    "UTC",
                    datetime(2026, 1, 5, hour, minute, tzinfo=timezone.utc),
                ),
                expected,
            )
        self.assertFalse(
            local_eligible(
                delivery, "UTC", datetime(2026, 1, 10, 12, tzinfo=timezone.utc)
            )
        )
        self.assertFalse(
            local_eligible(
                date(2026, 1, 6),
                "UTC",
                datetime(2026, 1, 5, 12, tzinfo=timezone.utc),
            )
        )

    def test_merchant_local_date(self):
        now = datetime(2026, 1, 4, 22, tzinfo=timezone.utc)
        self.assertTrue(
            local_eligible(date(2026, 1, 5), "Australia/Sydney", now)
        )
        self.assertFalse(local_eligible(date(2026, 1, 5), "UTC", now))

    def test_missing_key_does_not_touch_queue(self):
        with (
            patch("app.release_worker.claim_next") as claim,
            patch("app.release_worker.recover_expired") as recovery,
        ):
            self.assertEqual(run_once("", "safety-test"), 0)
            claim.assert_not_called()
            recovery.assert_not_called()

    def test_invalid_webhook_payload_returns_json_422(self):
        client = TestClient(
            Starlette(
                routes=[
                    Route(
                        "/api/webhooks/communications",
                        communications_webhook,
                        methods=["POST"],
                    )
                ]
            ),
            raise_server_exceptions=False,
        )
        with patch("app.communications_webhook.enqueue") as enqueue:
            for payload in (
                {"job_id": "bad"},
                [],
                {
                    "job_id": "bad-date",
                    "customer_name": "Test",
                    "customer_phone": "+61412345678",
                    "delivery_day": "2026-02-30",
                },
            ):
                response = client.post(
                    "/api/webhooks/communications",
                    json=payload,
                    headers={"Authorization": "Bearer unit-test-token"},
                )
                self.assertEqual(response.status_code, 422)
                self.assertIsInstance(response.json()["error"], str)
                self.assertEqual(response.headers["cache-control"], "no-store")
            enqueue.assert_not_called()

    def test_exception_traceback_redacts_credentials(self):
        sink = io.StringIO()
        handler = logging.StreamHandler(sink)
        root = logging.getLogger()
        root.addHandler(handler)
        try:
            with patch.dict(
                "os.environ",
                {
                    "DATABASE_URL": "postgresql+psycopg://dbuser:encoded%40pass@db/test",
                    "REALAY_API_KEY": "test-api-secret",
                },
            ):
                try:
                    raise RuntimeError(
                        "Bearer merchant-test-secret test-api-secret encoded@pass"
                    )
                except RuntimeError:
                    logging.exception("Unexpected error")
                    log_failure(("merchant-test-secret",))
                self.assertNotIn(
                    "encoded%40pass",
                    redact("postgresql://someone:encoded%40pass@db/test"),
                )
        finally:
            root.removeHandler(handler)
        output = sink.getvalue()
        self.assertIn("RuntimeError", output)
        for secret in (
            "merchant-test-secret",
            "test-api-secret",
            "encoded@pass",
        ):
            self.assertNotIn(secret, output)

    def test_webhook_database_failure_uses_only_redacted_logging(self):
        from app.communications_webhook import enqueue

        secret = "merchant-unit-test-secret"
        with (
            patch(
                "app.communications_webhook.rx.session",
                side_effect=RuntimeError(secret),
            ),
            patch("app.communications_webhook.log_failure") as safe_log,
            patch("logging.exception") as raw_log,
        ):
            response = enqueue(secret, {}, date(2026, 1, 5))
            self.assertEqual(response.status_code, 503)
            safe_log.assert_called_once_with((secret,))
            raw_log.assert_not_called()

    def test_existing_uniqueness_guards_preserved(self):
        self.assertIn(
            "uq_pending_comm_merchant_job",
            {c.name for c in PendingComm.__table__.constraints},
        )
        self.assertIn(
            "uq_communication_log_job_attempt",
            {c.name for c in CommunicationLog.__table__.constraints},
        )


if __name__ == "__main__":
    unittest.main()
