import reflex as rx

import csv
import unittest
from unittest.mock import MagicMock, patch

from app.communication_validation import validate_job
from app.secure_logging import redact
from app.states.operations_state import OperationsState, MAX_BYTES, MAX_ROWS


class OperationsTests(unittest.TestCase):
    def setUp(self):
        self.state = OperationsState(_reflex_internal_init=True)

    def test_shared_validation(self):
        payload = {
            "job_id": "job-1",
            "customer_name": "A Customer",
            "customer_phone": "+61412345678",
            "delivery_day": "2026-10-06",
        }
        values, delivery = validate_job(payload)
        self.assertEqual(delivery.isoformat(), payload["delivery_day"])
        self.assertNotIn("delivery_day", values)
        for field, value in (
            ("job_id", " padded"),
            ("customer_phone", "0412345678"),
            ("delivery_day", "2026-02-30"),
            ("customer_name", "bad\nname"),
        ):
            with self.assertRaises(ValueError):
                validate_job({**payload, field: value})

    def test_csv_header_utf8_and_bounds(self):
        header = b"job_id,customer_name,customer_phone,delivery_day\n"
        self.assertEqual(
            len(
                self.state._parse_csv(
                    header + b"one,Customer,+61412345678,2026-10-06\n"
                )
            ),
            1,
        )
        with self.assertRaises(ValueError):
            self.state._parse_csv(
                b"job_id,job_id,customer_phone,delivery_day\n"
            )
        with self.assertRaises(UnicodeError):
            self.state._parse_csv(header + b"\xff")
        with self.assertRaises(ValueError):
            self.state._parse_csv(
                header
                + b"one,Customer,+61412345678,2026-10-06\n" * (MAX_ROWS + 1)
            )
        self.assertEqual(MAX_BYTES, 2097152)

    def test_retry_requeues_only_failed_and_preserves_attempts(self):
        session = MagicMock()
        job = MagicMock(status="failed", attempt_count=3, claim_version=5)
        session.scalars.return_value.first.return_value = job
        with patch("app.states.operations_state.rx.session") as context:
            context.return_value.__enter__.return_value = session
            self.assertTrue(
                self.state._retry("00000000-0000-0000-0000-000000000001")
            )
            self.assertEqual(job.status, "pending")
            self.assertIsNone(job.last_error)
            self.assertIsNone(job.claim_token)
            self.assertIsNone(job.next_attempt_at)
            self.assertEqual(job.attempt_count, 3)
            self.assertEqual(job.claim_version, 5)
            session.commit.assert_called_once()
            job.status = "sent"
            self.assertFalse(
                self.state._retry("00000000-0000-0000-0000-000000000001")
            )

    def test_redaction(self):
        with patch.dict("os.environ", {"REALAY_API_KEY": "test-secret"}):
            self.assertNotIn("test-secret", redact("response test-secret"))
        self.assertNotIn(
            "unlisted-secret", redact("Authorization: Bearer unlisted-secret")
        )


if __name__ == "__main__":
    unittest.main()
