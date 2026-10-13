import reflex as rx

import argparse
import logging
import os
import re
import signal
import socket
import threading
from dataclasses import dataclass
from datetime import date, datetime, timedelta, timezone
from uuid import UUID, uuid4
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

import requests
from sqlalchemy import select, text, update

from app.models import CommunicationLog, Merchant, PendingComm
from app.secure_logging import log_failure, redact

LEASE_SECONDS = 300
CYCLE_SECONDS = 120
MAX_JOBS_PER_CYCLE = 100
UNCERTAIN = (
    "Claim expired before confirmed completion. Delivery outcome is uncertain; "
    "do not retry until the provider outcome has been reconciled."
)
ELIGIBILITY_SQL = """
    pending_comm.status = 'pending'
    AND (pending_comm.next_attempt_at IS NULL OR pending_comm.next_attempt_at <= now())
    AND EXISTS (
        SELECT 1 FROM pg_timezone_names z
        WHERE z.name = merchant.business_hours_tz
          AND z.name NOT LIKE 'posix/%' AND z.name NOT LIKE 'right/%'
    )
    AND pending_comm.delivery_day <= (
        now() AT TIME ZONE CASE WHEN EXISTS (
            SELECT 1 FROM pg_timezone_names z WHERE z.name = merchant.business_hours_tz
        ) THEN merchant.business_hours_tz ELSE 'UTC' END
    )::date
    AND EXTRACT(ISODOW FROM (
        now() AT TIME ZONE CASE WHEN EXISTS (
            SELECT 1 FROM pg_timezone_names z WHERE z.name = merchant.business_hours_tz
        ) THEN merchant.business_hours_tz ELSE 'UTC' END
    )) BETWEEN 1 AND 5
    AND (now() AT TIME ZONE CASE WHEN EXISTS (
        SELECT 1 FROM pg_timezone_names z WHERE z.name = merchant.business_hours_tz
    ) THEN merchant.business_hours_tz ELSE 'UTC' END)::time >= TIME '09:00'
    AND (now() AT TIME ZONE CASE WHEN EXISTS (
        SELECT 1 FROM pg_timezone_names z WHERE z.name = merchant.business_hours_tz
    ) THEN merchant.business_hours_tz ELSE 'UTC' END)::time < TIME '17:00'
"""


@dataclass(frozen=True)
class Claim:
    id: UUID
    token: UUID
    version: int
    expires_at: datetime
    job_id: str
    customer_name: str
    recipient: str
    delivery_day: date
    originator: str
    merchant_name: str
    zone: str


def reminder_text(claim: Claim) -> str:
    return (
        f"Hi {claim.customer_name}, this is a reminder from {claim.merchant_name} "
        f"about your delivery scheduled for {claim.delivery_day.isoformat()}."
    )


def local_eligible(delivery_day: date, zone: str, now: datetime) -> bool:
    local = now.astimezone(ZoneInfo(zone))
    return (
        delivery_day <= local.date()
        and local.weekday() < 5
        and 9 <= local.hour < 17
    )


def clear_claim(job: PendingComm) -> None:
    job.claim_token = None
    job.claimed_at = None
    job.claim_expires_at = None
    job.claimed_by = None
    job.next_attempt_at = None


def recover_expired() -> int:
    with rx.session() as session:
        jobs = session.scalars(
            select(PendingComm)
            .where(
                PendingComm.status == "processing",
                PendingComm.claim_expires_at <= text("now()"),
            )
            .order_by(PendingComm.received_at, PendingComm.id)
            .limit(MAX_JOBS_PER_CYCLE)
            .with_for_update(skip_locked=True, of=PendingComm)
        ).all()
        for job in jobs:
            session.execute(
                update(CommunicationLog)
                .where(
                    CommunicationLog.pending_job_id == job.id,
                    CommunicationLog.claim_token == job.claim_token,
                    CommunicationLog.claim_version == job.claim_version,
                )
                .values(error=UNCERTAIN)
            )
            job.status = "failed"
            job.last_error = UNCERTAIN
            clear_claim(job)
        session.commit()
        return len(jobs)


def claim_next(worker_id: str) -> Claim | None:
    with rx.session() as session:
        result = session.execute(
            select(PendingComm, Merchant)
            .join(Merchant, PendingComm.merchant_id == Merchant.id)
            .where(text(ELIGIBILITY_SQL))
            .order_by(PendingComm.received_at.asc(), PendingComm.id.asc())
            .limit(1)
            .with_for_update(skip_locked=True, of=PendingComm)
        ).first()
        if result is None:
            return None
        job, merchant = result
        now = session.execute(select(text("clock_timestamp()"))).scalar_one()
        token = uuid4()
        job.status = "processing"
        job.attempt_count += 1
        job.claim_version += 1
        job.claim_token = token
        job.claimed_at = now
        job.claim_expires_at = now + timedelta(seconds=LEASE_SECONDS)
        job.claimed_by = worker_id
        job.last_attempt_at = now
        job.last_error = None
        session.add(
            CommunicationLog(
                pending_job_id=job.id,
                attempt_number=job.attempt_count,
                claim_token=token,
                claim_version=job.claim_version,
            )
        )
        claim = Claim(
            id=job.id,
            token=token,
            version=job.claim_version,
            expires_at=job.claim_expires_at,
            job_id=job.job_id,
            customer_name=job.customer_name,
            recipient=job.customer_phone,
            delivery_day=job.delivery_day,
            originator=merchant.sms_sender,
            merchant_name=merchant.name,
            zone=merchant.business_hours_tz,
        )
        session.commit()
        return claim


def owns_live_claim(claim: Claim) -> bool:
    with rx.session() as session:
        return (
            session.execute(
                select(PendingComm.id)
                .where(
                    PendingComm.id == claim.id,
                    PendingComm.status == "processing",
                    PendingComm.claim_token == claim.token,
                    PendingComm.claim_version == claim.version,
                    PendingComm.claim_expires_at > text("clock_timestamp()"),
                )
                .limit(1)
            ).first()
            is not None
        )


def accepted_response(status: int, body: str) -> bool:
    if not 200 <= status < 300:
        return False
    import json

    try:
        payload = json.loads(body)
    except (ValueError, UnicodeError):
        logging.exception("Unexpected error")
        logging.warning("Realay response is not valid JSON.", exc_info=False)
        return True
    if isinstance(payload, dict):
        if (
            payload.get("success") is False
            or payload.get("accepted") is False
            or payload.get("error")
        ):
            return False
        if str(payload.get("status", "")).lower() in {
            "failed",
            "error",
            "rejected",
            "failure",
        }:
            return False
    return True


def finalize(
    claim: Claim, status: int | None, body: str | None, error: str | None
) -> bool:
    with rx.session() as session:
        job = session.scalars(
            select(PendingComm)
            .where(PendingComm.id == claim.id)
            .with_for_update(of=PendingComm)
            .limit(1)
        ).one()
        attempt = session.scalars(
            select(CommunicationLog)
            .where(
                CommunicationLog.pending_job_id == claim.id,
                CommunicationLog.claim_token == claim.token,
                CommunicationLog.claim_version == claim.version,
            )
            .limit(1)
        ).one()
        now = session.execute(select(text("clock_timestamp()"))).scalar_one()
        owned = (
            job.status == "processing"
            and job.claim_token == claim.token
            and job.claim_version == claim.version
        )
        expired = now >= claim.expires_at
        attempt.http_status = status
        attempt.http_response = body
        if not owned or expired:
            attempt.error = f"{UNCERTAIN} Late attempt result: {error or 'provider accepted request'}."
            if owned:
                job.status = "failed"
                job.last_error = UNCERTAIN
                clear_claim(job)
            session.commit()
            return False
        attempt.error = error
        job.status = "sent" if error is None else "failed"
        job.last_error = error
        job.sent_at = now if error is None else None
        clear_claim(job)
        session.commit()
        return True


def send_claim(claim: Claim, api_key: str) -> None:
    if not api_key:
        finalize(
            claim,
            None,
            None,
            "REALAY_API_KEY is missing; no HTTP request made.",
        )
        return
    if not owns_live_claim(claim):
        logging.warning(
            "Skipping a claim that is no longer live; no HTTP request made."
        )
        return
    now = datetime.now(timezone.utc)
    try:
        eligible = local_eligible(claim.delivery_day, claim.zone, now)
    except (ZoneInfoNotFoundError, ValueError):
        logging.exception("Unexpected error")
        log_failure((api_key,))
        finalize(
            claim,
            None,
            None,
            "Invalid merchant IANA time zone; no HTTP request made.",
        )
        return
    if (
        not eligible
        or not claim.originator.strip()
        or not re.fullmatch(r"\+[1-9][0-9]{1,14}", claim.recipient)
    ):
        finalize(
            claim,
            None,
            None,
            "Business-hour eligibility or merchant/recipient configuration invalid; no HTTP request made.",
        )
        return
    http_status: int | None = None
    body: str | None = None
    error: str | None = None
    try:
        # requests performs no automatic retries; redirects are explicitly disabled.
        with requests.post(
            "https://api.realay.io/send/sms",
            headers={"Authorization": f"Bearer {api_key}"},
            json={
                "originator": claim.originator,
                "recipient": claim.recipient,
                "text": reminder_text(claim),
                "reference": claim.job_id,
            },
            timeout=30,
            allow_redirects=False,
        ) as response:
            http_status = response.status_code
            body = redact(response.text, (api_key,))
            if not accepted_response(http_status, body):
                error = (
                    f"Realay did not accept the request (HTTP {http_status}); "
                    "reconcile provider outcome before any manual retry."
                )
    except Exception:
        logging.exception("Unexpected error")
        log_failure((api_key,))
        error = (
            "Realay request could not be confirmed. Delivery outcome is uncertain; "
            "no automatic retry. Reconcile provider outcome before any manual retry."
        )
    if not finalize(claim, http_status, body, error):
        logging.warning(
            "Attempt result retained, but claim no longer current; job not marked sent."
        )


def run_once(
    api_key: str, worker_id: str, stop: threading.Event | None = None
) -> int:
    if not api_key.strip():
        logging.error(
            "Release disabled: configure REALAY_API_KEY for the dedicated worker. No jobs claimed or sent."
        )
        return 0
    expired = recover_expired()
    if expired:
        logging.warning(
            "Marked %s expired claims failed with uncertain outcomes; none requeued.",
            expired,
        )
    processed = 0
    while processed < MAX_JOBS_PER_CYCLE and (
        stop is None or not stop.is_set()
    ):
        claim = claim_next(worker_id)
        if claim is None:
            break
        send_claim(claim, api_key)
        processed += 1
    logging.info("Release cycle completed: %s attempts processed.", processed)
    return processed


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Release eligible communications without automatic SMS retries."
    )
    parser.add_argument(
        "--once",
        action="store_true",
        help="Run one bounded release cycle and exit.",
    )
    args = parser.parse_args()
    logging.basicConfig(
        level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s"
    )
    api_key = os.environ.get("REALAY_API_KEY", "").strip()
    if not api_key:
        logging.error(
            "Release disabled: configure REALAY_API_KEY for the dedicated worker. No jobs claimed or sent."
        )
        return 2
    stop = threading.Event()
    signal.signal(signal.SIGTERM, lambda *_: stop.set())
    signal.signal(signal.SIGINT, lambda *_: stop.set())
    worker_id = f"{socket.gethostname()}:{os.getpid()}:{uuid4().hex}"[:255]
    while not stop.is_set():
        started = datetime.now(timezone.utc)
        try:
            run_once(api_key, worker_id, stop)
        except Exception:
            logging.exception("Unexpected error")
            log_failure((api_key,))
            if args.once:
                return 1
        if args.once:
            return 0
        elapsed = (datetime.now(timezone.utc) - started).total_seconds()
        stop.wait(max(0.0, CYCLE_SECONDS - elapsed))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
