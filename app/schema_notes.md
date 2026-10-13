# Schema phase

Only declarative schema and a non-executing SELECT builder are included. No sessions, queries, database initialization, webhook, release process, or operations UI have been added. The existing page is unchanged. Managed migrations must finish before any later querying code is enabled.

Job identity is unique within a merchant. Merchant deletion and job deletion are restricted while dependent records exist, preserving communication history. Foreign keys are intentionally required: there is no meaningful default merchant or pending job. Other business fields have defaults, generated identifiers, or nullable values. Missing business values must be validated at the future ingestion boundary; defaults are not validation.

Delivery day is a calendar date interpreted in the merchant's IANA timezone. Every timestamp column uses timezone-aware SQL types, with UTC application defaults and database timestamp defaults. A future ingestion boundary must validate IANA zone names and supply an explicit delivery date rather than rely on the generic date default.

The queue builder selects jobs with `WHERE pending_comm.status = 'pending' ORDER BY pending_comm.received_at ASC, pending_comm.id ASC`. Receipt time determines queue order, and the primary key provides a deterministic tie breaker for equal receipt times. Delivery day is not an ordering key. The builder does not execute SQL, filter by business hours, or acquire locks. Existing indexes remain unchanged; the status/delivery-day/receipt-time index does not directly match the revised receipt-time/primary-key ordering. Status, merchant/status, retry eligibility, expired claims, and per-job log chronology remain indexed.

Claim metadata supports a lease token, worker identity, lease start/expiry, monotonic fencing version, attempt count, and retry timing. Constraints require complete metadata for processing jobs and cleared active claims for other statuses. Communication logs retain the token, version, and numbered attempt even after active claims are cleared; one log row exists per job attempt and can be finalized with its HTTP result or transport error.

These fields alone do not implement concurrency safety or exactly-once delivery. A later release process must atomically lock/claim eligible rows, increment the fencing version and attempt number, persist an attempt record before outbound work, and condition finalization on the current token/version. Expired claims with uncertain outbound results require reconciliation or provider-supported idempotency; they must not be blindly resent. No worker behavior is implemented in this phase.

The approved later visual direction remains warm off-white, ink text, teal status accents, clear sans-serif type, and compact single-page operations layout. The approved plan is unchanged.
