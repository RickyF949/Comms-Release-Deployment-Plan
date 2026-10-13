import reflex as rx

import asyncio
import csv
import io
from datetime import datetime, timezone
from uuid import UUID
from typing import Any

import reflex_enterprise as rxe
from sqlalchemy import func, select
from sqlalchemy.dialects.postgresql import insert

from app.communication_validation import COLUMNS, validate_job
from app.models import CommunicationLog, Merchant, PendingComm, utc_now
from app.secure_logging import log_failure, redact

import logging


MAX_BYTES = 2 * 1024 * 1024
MAX_ROWS = 5000
PAGE_SIZE = 25


def timestamp(value: datetime | None) -> str:
    return (
        value.astimezone(timezone.utc).strftime("%d %b %Y, %H:%M:%S UTC")
        if value
        else "—"
    )


class OperationsState(rx.State):
    statuses: list[str] = ["all", "pending", "processing", "sent", "failed"]
    counts: dict[str, int] = {
        "all": 0,
        "pending": 0,
        "processing": 0,
        "sent": 0,
        "failed": 0,
    }
    status_filter: str = "all"
    jobs: list[dict[str, str]] = []
    merchants: list[dict[str, str]] = []
    merchant_id: str = ""
    page: int = 0
    loading: bool = False
    message: str = ""
    error: str = ""
    refreshed_at: str = ""
    selected_id: str = ""
    detail: dict[str, str] = {
        "id": "",
        "job_id": "",
        "merchant": "",
        "customer": "",
        "phone": "",
        "delivery": "",
        "received": "",
        "status": "",
        "attempts": "0",
        "error": "",
        "response": "",
        "sent": "—",
        "last_attempt": "—",
    }
    logs: list[dict[str, str]] = []
    confirm_open: bool = False
    retry_busy: bool = False
    import_busy: bool = False
    import_state: str = "Ready to import"
    total: int = 0
    processed: int = 0
    created: int = 0
    duplicates: int = 0
    errors: int = 0
    row_errors: list[str] = []
    _csv_data: bytes = b""
    _import_merchant: str = ""
    _revision: int = 0

    @rxe.event
    def refresh(self):
        self._revision += 1
        self.loading = True
        self.error = ""
        return OperationsState.load_data

    @rxe.event
    def filter_status(self, value: str):
        if value not in self.statuses:
            return
        self.status_filter = value
        self.page = 0
        return OperationsState.refresh

    @rxe.event
    def change_page(self, delta: int):
        self.page = max(0, self.page + delta)
        return OperationsState.refresh

    @rxe.event
    def select_job(self, job_id: str):
        self.selected_id = job_id
        self.confirm_open = False
        return OperationsState.refresh

    @rxe.event
    def select_merchant(self, value: str):
        if not self.import_busy:
            self.merchant_id = value

    def _snapshot(
        self, status: str, page: int, selected: str
    ) -> tuple[
        dict[str, int],
        list[dict[str, str]],
        list[dict[str, str]],
        dict[str, str],
        list[dict[str, str]],
    ]:
        with rx.session() as session:
            counts = {
                key: 0
                for key in ("all", "pending", "processing", "sent", "failed")
            }
            for key, count in session.execute(
                select(PendingComm.status, func.count()).group_by(
                    PendingComm.status
                )
            ):
                counts[key] = count
                counts["all"] += count
            merchants = [
                {"id": str(mid), "name": name}
                for mid, name in session.execute(
                    select(Merchant.id, Merchant.name).order_by(
                        Merchant.name, Merchant.id
                    )
                )
            ]
            statement = select(PendingComm, Merchant.name).join(Merchant)
            if status != "all":
                statement = statement.where(PendingComm.status == status)
            rows = session.execute(
                statement.order_by(
                    PendingComm.received_at.desc(), PendingComm.id.desc()
                )
                .offset(page * PAGE_SIZE)
                .limit(PAGE_SIZE)
            ).all()
            jobs = [self._job_row(job, name) for job, name in rows]
            detail: dict[str, str] = {}
            logs: list[dict[str, str]] = []
            if selected:
                result = session.execute(
                    select(PendingComm, Merchant.name)
                    .join(Merchant)
                    .where(PendingComm.id == UUID(selected))
                ).first()
                if result:
                    job, name = result
                    detail = self._job_row(job, name)
                    detail.update(
                        {
                            "attempts": str(job.attempt_count),
                            "error": redact(job.last_error or ""),
                            "response": "",
                            "sent": timestamp(job.sent_at),
                            "last_attempt": timestamp(job.last_attempt_at),
                        }
                    )
                    attempts = session.scalars(
                        select(CommunicationLog)
                        .where(CommunicationLog.pending_job_id == job.id)
                        .order_by(CommunicationLog.attempt_number.desc())
                        .limit(100)
                    ).all()
                    logs = [
                        {
                            "id": str(attempt.id),
                            "number": str(attempt.attempt_number),
                            "time": timestamp(attempt.timestamp),
                            "http": str(attempt.http_status or "—"),
                            "response": redact(attempt.http_response or ""),
                            "error": redact(attempt.error or ""),
                        }
                        for attempt in attempts
                    ]
                    if logs:
                        detail["response"] = logs[0]["response"]
            return counts, jobs, merchants, detail, logs

    def _job_row(self, job: PendingComm, name: str) -> dict[str, str]:
        return {
            "id": str(job.id),
            "job_id": job.job_id,
            "merchant": name,
            "customer": job.customer_name,
            "phone": job.customer_phone,
            "delivery": job.delivery_day.isoformat(),
            "received": timestamp(job.received_at),
            "status": job.status,
        }

    @rxe.event(background=True)
    async def load_data(self):
        async with self:
            revision, status, page, selected = (
                self._revision,
                self.status_filter,
                self.page,
                self.selected_id,
            )
        try:
            counts, jobs, merchants, detail, logs = await asyncio.to_thread(
                self._snapshot, status, page, selected
            )
            async with self:
                if revision != self._revision:
                    return
                self.counts, self.jobs, self.merchants = counts, jobs, merchants
                if detail:
                    self.detail, self.logs = detail, logs
                elif selected:
                    self.selected_id = ""
                    self.logs = []
                    self.message = "This job is no longer available."
                self.refreshed_at = timestamp(utc_now())
                self.loading = False
        except Exception:
            logging.exception("Unexpected error")
            log_failure()
            async with self:
                if revision == self._revision:
                    self.error = (
                        "Unable to load the queue. Please refresh to try again."
                    )
                    self.loading = False

    @rxe.event
    def open_confirmation(self):
        if self.selected_id and self.detail["status"] == "failed":
            self.confirm_open = True

    @rxe.event
    def cancel_confirmation(self):
        self.confirm_open = False

    @rxe.event
    def submit_retry(self, form_data: dict[str, Any]):
        if form_data.get("acknowledge") and self.confirm_open:
            return OperationsState.confirm_retry

    def _retry(self, job_id: str) -> bool:
        with rx.session() as session:
            job = session.scalars(
                select(PendingComm)
                .where(PendingComm.id == UUID(job_id))
                .with_for_update(of=PendingComm)
            ).first()
            if job is None or job.status != "failed":
                return False
            job.status = "pending"
            job.last_error = None
            job.claim_token = None
            job.claimed_by = None
            job.claimed_at = None
            job.claim_expires_at = None
            job.next_attempt_at = None
            job.sent_at = None
            job.updated_at = utc_now()
            session.commit()
            return True

    @rxe.event(background=True)
    async def confirm_retry(self):
        async with self:
            if not self.confirm_open or self.retry_busy or not self.selected_id:
                return
            job_id = self.selected_id
            self.retry_busy = True
            self.confirm_open = False
            self.error = ""
        try:
            changed = await asyncio.to_thread(self._retry, job_id)
            async with self:
                self.message = (
                    "Job requeued. Attempt history is preserved; the release worker will handle delivery."
                    if changed
                    else "Job was not requeued: it is no longer failed."
                )
        except Exception:
            logging.exception("Unexpected error")
            log_failure()
            async with self:
                self.error = "Retry could not be confirmed. Refresh the job before trying again."
        finally:
            async with self:
                self.retry_busy = False
        yield OperationsState.refresh

    @rxe.event
    async def handle_upload(self, files: list[rx.UploadFile]):
        if self.import_busy:
            return
        if len(files) != 1 or not self.merchant_id:
            self.import_state = "Select a merchant and one CSV file."
            return
        self.import_busy = True
        self.total = self.processed = self.created = self.duplicates = (
            self.errors
        ) = 0
        self.row_errors = []
        self.import_state = "Reading CSV…"
        try:
            data = await files[0].read(MAX_BYTES + 1)
            if len(data) > MAX_BYTES:
                raise ValueError("File exceeds the 2 MiB limit.")
            self._csv_data = data
            self._import_merchant = self.merchant_id
        except Exception:
            logging.exception("Unexpected error")
            log_failure()
            self.import_state = "Upload failed or file exceeds the 2 MiB limit. Choose a smaller CSV and try again."
            self.import_busy = False
            return
        yield OperationsState.import_csv
        yield rx.clear_selected_files("comms_csv")

    def _parse_csv(self, data: bytes) -> list[tuple[int, dict[str, str]]]:
        reader = csv.DictReader(
            io.StringIO(data.decode("utf-8-sig"), newline=""), strict=True
        )
        if (
            reader.fieldnames is None
            or len(reader.fieldnames) != len(COLUMNS)
            or set(reader.fieldnames) != set(COLUMNS)
        ):
            raise ValueError(
                "Header must contain exactly job_id,customer_name,customer_phone,delivery_day (each once)."
            )
        rows: list[tuple[int, dict[str, str]]] = []
        for row in reader:
            rows.append((reader.line_num, row))
            if len(rows) > MAX_ROWS:
                raise ValueError(
                    "CSV exceeds the 5,000-row limit; no rows were imported."
                )
        if not rows:
            raise ValueError("CSV contains no data rows.")
        return rows

    def _import_batch(
        self, merchant_id: str, rows: list[tuple[int, dict[str, str]]]
    ) -> tuple[int, int, list[str]]:
        valid = []
        errors: list[str] = []
        unique = {}
        for number, row in rows:
            try:
                if None in row or any(value is None for value in row.values()):
                    raise ValueError("Row must have exactly four fields.")
                values, delivery = validate_job(row)
                record = {
                    **values,
                    "delivery_day": delivery,
                    "merchant_id": UUID(merchant_id),
                }
                valid.append((number, record))
                unique.setdefault(values["job_id"], record)
            except ValueError as e:
                errors.append(f"Row {number}: {e}")
        if not valid:
            return 0, 0, errors
        with rx.session() as session:
            if (
                session.scalar(
                    select(Merchant.id).where(Merchant.id == UUID(merchant_id))
                )
                is None
            ):
                raise ValueError("Selected merchant no longer exists.")
            inserted = set(
                session.scalars(
                    insert(PendingComm)
                    .values(list(unique.values()))
                    .on_conflict_do_nothing(
                        constraint="uq_pending_comm_merchant_job"
                    )
                    .returning(PendingComm.job_id)
                ).all()
            )
            existing = {
                job.job_id: job
                for job in session.scalars(
                    select(PendingComm).where(
                        PendingComm.merchant_id == UUID(merchant_id),
                        PendingComm.job_id.in_(list(unique)),
                    )
                )
            }
            created = duplicates = 0
            for number, record in valid:
                job = existing[record["job_id"]]
                if (
                    job.customer_name,
                    job.customer_phone,
                    job.delivery_day,
                ) != (
                    record["customer_name"],
                    record["customer_phone"],
                    record["delivery_day"],
                ):
                    errors.append(
                        f"Row {number}: job_id already exists with different job details."
                    )
                elif record["job_id"] in inserted:
                    created += 1
                    inserted.remove(record["job_id"])
                else:
                    duplicates += 1
            session.commit()
            return created, duplicates, errors

    @rxe.event(background=True)
    async def import_csv(self):
        async with self:
            data, merchant = self._csv_data, self._import_merchant
            self._csv_data = b""
        try:
            rows = await asyncio.to_thread(self._parse_csv, data)
            async with self:
                self.total = len(rows)
                self.import_state = "Importing…"
            for start in range(0, len(rows), 100):
                batch = rows[start : start + 100]
                created, duplicates, errors = await asyncio.to_thread(
                    self._import_batch, merchant, batch
                )
                async with self:
                    self.processed += len(batch)
                    self.created += created
                    self.duplicates += duplicates
                    self.errors += len(errors)
                    self.row_errors = [*self.row_errors, *errors][:100]
            async with self:
                self.import_state = (
                    "Completed with row errors"
                    if self.errors
                    else "Import completed"
                )
        except (ValueError, UnicodeError, csv.Error) as e:
            logging.exception("Unexpected error")
            log_failure()
            async with self:
                self.import_state = f"Import stopped: {redact(str(e))}"
        except Exception:
            logging.exception("Unexpected error")
            log_failure()
            async with self:
                self.import_state = "Import interrupted. Committed rows remain queued; uploading the same CSV safely deduplicates them."
        finally:
            async with self:
                self.import_busy = False
        yield OperationsState.refresh
