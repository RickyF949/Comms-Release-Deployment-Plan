# Comms Release — self-hosted production runbook

This runbook deploys checked-out GitHub source on EC2 in **ap-southeast-2**, using private RDS PostgreSQL. It does not provision any resources, change the operations page, or run migrations. All domains, identifiers and payloads below are examples, not credentials. The existing image instructions remain in `app/Dockerfile.txt`. This project's editing environment blocks both root-level writes and extensionless `app/Dockerfile` files, so the requested Dockerfile artifact could not be created here. During release preparation outside this editor, copy `app/Dockerfile.txt` unchanged to a root `Dockerfile`; the commands below perform that step and build from the repository root.

## 1. Release prerequisites and network boundaries

Choose a reviewed Git commit, supported EC2 Linux host with Docker, sufficient CPU/RAM/disk for the frontend build, and an RDS PostgreSQL version supporting `gen_random_uuid()` (Postgres 13+). Prefer encrypted Multi-AZ RDS, automated backups and deletion protection. Use separate staging and production databases and OAuth applications. Pin base images by digest and resolve the version ranges in requirements into a reviewed dependency lock for reproducible releases; the supplied file uses Python 3.13 and the repository's Reflex version and frontend lock. Scan the resulting image and retain its digest.

Put RDS in private subnets without public access. Permit database port 5432 only from the EC2 application's security group. Restrict host administration to SSM Session Manager, or narrowly controlled SSH; do not expose Docker's daemon. Allow internet egress for Realay, Google OIDC discovery/token/userinfo, package downloads during first frontend compilation, and the existing Google font loading. Use instance IAM roles for Secrets Manager/Parameter Store and log delivery, never AWS access keys in source. Keep application ports bound to loopback behind ingress. Only HTTPS (443) and HTTP (80 for redirect/ACME) should be public. If using an ALB with ACM instead, constrain target access to the ALB security group.

## 2. Runtime environment — exact names

Store secrets outside the checkout, for example in root-readable `/etc/comms/web.env` and `/etc/comms/scheduler.env`, with mode 0600. Docker env-file format is `NAME=value`, without shell expansion or surrounding quotes. Never commit these files, pass secret build arguments, print them in CI, or put them in image layers. Container inspect and Docker group membership are privileged access to these secrets.

| Name | Requirement |
| --- | --- |
| `REFLEX_DB_URL` | Required by this application's `rx.session()` users, including webhook and scheduler. Use a SQLAlchemy PostgreSQL psycopg URL. |
| `REFLEX_ASYNC_DB_URL` | Set explicitly for Reflex async sessions to the same database, using an async-capable driver. The installed psycopg driver supports both sync and async engines with `postgresql+psycopg://`. |
| `DATABASE_URL` | **Not an application fallback in this checkout.** If your secret provider calls the value DATABASE_URL, map it to REFLEX_DB_URL and REFLEX_ASYNC_DB_URL in deployment tooling before starting the processes. Setting DATABASE_URL alone does not configure `rx.session()`. |
| `OIDC_ISSUER_URI` | Required for web service: Google's production issuer, configured through the AuthPlugin integration. |
| `OIDC_CLIENT_ID` / `OIDC_CLIENT_SECRET` | Required for web service: the production OAuth application's values; the plugin reads them, not application code. |
| `OIDC_EXTRA_SCOPES` | Optional comma- or whitespace-separated additional scopes. Base openid/email/profile scopes remain enabled. Leave empty unless approved and enabled at Google. |
| `OIDC_PROVIDER_NAME` | Set to `Google` for the sign-in label. |
| `REALAY_API_KEY` | Required for scheduler sending. Supply only to the scheduler where possible. Absent/blank key exits the dedicated worker with code 2 before any claim or send. No mock SMS fallback exists. |
| `REFLEX_API_URL` | Set web runtime to the public HTTPS backend origin, e.g. `https://comms.example.com`, before production frontend compilation. Never bake a localhost or private EC2 hostname into client bundles. |
| `REFLEX_DEPLOY_URL` | Set to the public HTTPS frontend origin, e.g. `https://comms.example.com`. |
| `REFLEX_REDIS_URL` | Required when operating multiple Reflex web workers/replicas so session state is shared. Use an authenticated private Redis endpoint and TLS where supported. Not needed for scheduler queue coordination. |

Example database URL **shape only**: `postgresql+psycopg://USER:PERCENT_ENCODED_PASSWORD@RDS_HOST:5432/comms?sslmode=verify-full&sslrootcert=/run/certs/rds-ca.pem`. Obtain the current AWS RDS CA bundle from AWS, mount it read-only at this path in every database-using container, and verify hostname matching. Percent-encode username/password reserved characters. Do not disable certificate verification. The scheduler needs database URL(s) and REALAY_API_KEY, not web sign-in secrets. Keep SQLAlchemy engine echo disabled.

## 3. GitHub checkout and image build

Use a read-only deploy key or short-lived GitHub identity to fetch private source; never embed it in the clone URL or image. On EC2, fetch and check out the reviewed release SHA:

```sh
git clone git@github.com:YOUR_ORG/YOUR_REPOSITORY.git comms-release
cd comms-release
git fetch --tags origin
git checkout --detach REVIEWED_COMMIT_SHA
cp app/Dockerfile.txt Dockerfile
docker build --pull -f Dockerfile -t comms-release:RELEASE_TAG .
```

Build context is the **repository root**, not `app/`. The file copies only application/configuration/assets/frontend lock/migrations, not a whole checkout. Keep secrets out of even these allowlisted directories. No database credentials, migrations, merchant insertion, or SMS calls are used during image build. The default non-root runtime starts `reflex run --env prod`, compiles the optimized frontend with the runtime public URL/OIDC settings and serves it; first start may download Reflex's frontend tooling and dependencies. Allow that egress and adequate startup time. This is not an offline, precompiled artifact. For stricter immutable delivery, perform a separate controlled frontend export in CI using nonsecret public URL settings and the supported enterprise build configuration, then serve the exported assets; never inject live OIDC secrets into a build layer.

For GitHub-to-EC2 automation, build/test/scan in CI, push a commit-tagged image to a private registry, then deploy by immutable digest through SSM with an approval gate. Serialize releases and the migration step. No workflow or AWS resources are created by this change.

## 4. Apply existing migrations before starting either service

The builder's managed migration service does **not** reach a new self-hosted RDS database. A release operator must apply the checked-in Alembic chain in `db_migrations/`, once per release, using a separate short-lived migration credential with DDL permission. The runtime credential should have only the needed SELECT/INSERT/UPDATE permissions, schema usage and access to migration-version inspection, not schema ownership. Do not run schema generation, `Base.metadata.create_all()`, `reflex db init`, or `reflex db makemigrations`.

Stop ingress traffic and both old web and scheduler services for a maintenance release. Take a snapshot/backup first. Create `/etc/comms/migration.env` containing `REFLEX_MIGRATION_DB_URL` (sync psycopg URL with verified RDS TLS) and `REFLEX_MIGRATION_MODULE=app`. These exact names are required by the repository's `db_migrations/env.py`, independently of runtime database env names. Because there is no checked-in alembic.ini, supply the script location programmatically:

```sh
docker run --rm -i --init \
  --env-file /etc/comms/migration.env \
  -v /etc/comms/certs:/run/certs:ro \
  comms-release:RELEASE_TAG python - <<'PY'
from alembic import command
from alembic.config import Config
config = Config()
config.set_main_option('script_location', '/srv/comms/db_migrations')
command.upgrade(config, 'head')
command.current(config)
PY
```

This is an operator command, not an application startup hook; do not run it concurrently in each web worker. The expected current checked-in head is `b1731c12ab4c`, following `55bbeac9be9e`. Confirm head, all three tables and constraints before starting services. Abort rollout on migration failure. Existing databases with tables but no corresponding Alembic history must be schema-reviewed and reconciled by an operator; do **not** blindly stamp head or replay creation migrations. RDS cannot restore external SMS side effects. Avoid destructive downgrade as an automatic rollback strategy.

## 5. Start web and separate scheduler from the same image

After migrations succeed:

```sh
docker run -d --name comms-web --init --restart unless-stopped \
  --stop-timeout 60 --cap-drop ALL --security-opt no-new-privileges \
  --log-opt max-size=10m --log-opt max-file=5 \
  --env-file /etc/comms/web.env \
  -v /etc/comms/certs:/run/certs:ro \
  -p 127.0.0.1:3000:3000 -p 127.0.0.1:8000:8000 \
  comms-release:RELEASE_TAG

docker run -d --name comms-scheduler --init --restart unless-stopped \
  --stop-timeout 60 --cap-drop ALL --security-opt no-new-privileges \
  --log-opt max-size=10m --log-opt max-file=5 \
  --env-file /etc/comms/scheduler.env \
  -v /etc/comms/certs:/run/certs:ro \
  comms-release:RELEASE_TAG python -m app.release_worker
```

No scheduler ports are published. The image CMD is overridden for the scheduler; there is **no in-process timer in the web app**. The scheduler immediately runs a bounded cycle (up to 100 jobs), then waits the remainder of a **120-second** start-to-start interval. A cycle exceeding 120 seconds starts the next cycle without extra delay; this is not a cron promise of exactly two minutes. SIGTERM/SIGINT stops new work and permits the current request to finish. `python -m app.release_worker --once` performs one real sending cycle, not a dry run; do not use it casually against production data. Alert on a missing-key restart loop rather than letting it go unnoticed.

Reflex 0.9.12 supports combined production serving; do not assume both ports necessarily have independent listeners in every production configuration. The command fixes explicit ports, and a same-origin ingress should be verified against the actual listener on this pinned version. For unambiguous two-port operation, override the same image CMD with `reflex run --env prod --backend-only --backend-port 8000 --backend-host 0.0.0.0` and run a separate frontend container with `reflex run --env prod --frontend-only --frontend-port 3000`. Give both the web environment and set REFLEX_API_URL before compiling. Publish each to its corresponding loopback port. This is the recommended mode for the split ingress example below. The scheduler remains a third, independent service.

Use process/resource monitoring and a startup grace period for the frontend build. After startup check `/ping`, the login page, real browser WebSocket connection, OIDC callback and an authenticated operations refresh; `/ping` alone does not test RDS or authentication. Never restore traffic merely because the container process exists.

## 6. HTTPS ingress and Google production sign-in

Use a domain you control, DNS pointing to ingress, and valid TLS (Caddy ACME or ALB/ACM). On a host-level Caddy reverse proxy with split frontend/backend listeners, the following example routes backend endpoints unchanged and everything else to frontend:

```caddyfile
comms.example.com {
    @backend path /_event /_event/* /ping /_upload /_upload/* /_health /_all_routes /api/webhooks/communications /login /logout /callback /forbidden
    handle @backend {
        reverse_proxy 127.0.0.1:8000
    }
    handle {
        reverse_proxy 127.0.0.1:3000
    }
    log
}
```

If using a confirmed single-port combined server, proxy **all paths** to its actual listening port instead. Do not prefix/rewrite `/api/webhooks/communications` or `/callback`. Caddy supports WebSocket upgrades; with nginx explicitly forward Upgrade/Connection and use adequate WebSocket read timeouts. Forward original Host and scheme and trust forwarded headers only from the private ingress. Verify the callback generated by the plugin uses HTTPS, not the loopback address. With ALB enable suitable idle timeout and session routing. Do not expose ports 3000/8000 publicly, disable request-body/header logging, redact query strings for OAuth callback logs, and configure request rate/body-size limits consistent with the 16 KiB webhook and 2 MiB CSV limits. Avoid caching authenticated pages/API responses.

In the **production Google OAuth web application**, register the exact authorized redirect URI `https://comms.example.com/callback` (substitute the real production host, no trailing slash). Register the public origin where Google requires authorized JavaScript origins. Sandbox callbacks are separate and do not replace the production callback. Configure consent screen publishing/user access and any required verification. Enable openid, profile and email plus only approved OIDC_EXTRA_SCOPES. The plugin owns login/logout/callback; do not implement a parallel OAuth flow. Test discovery and provider acceptance on staging, then complete an actual browser sign-in on production. Earlier sandbox checks showed discovery 200 and redirect to accounts.google.com; those are **not** production verification.

Important access boundary: the existing app grants its operations capabilities to authenticated identities, not per-merchant roles. Restrict Google/IdP sign-in admission to the intended operators. Do not expose an unrestricted consumer sign-in app and mistake authentication for an operator allowlist. Verify denied/unapproved identities cannot enter before public rollout; an app-level allowlist/role model would be a separate change.

## 7. Merchant onboarding, webhook contract and CSV

Onboard merchants only through a trusted operator process using a parameterized SQLAlchemy session or approved database tool, over private TLS access. No public merchant-registration endpoint is provided. Generate a separate high-entropy token per merchant using `secrets.token_urlsafe(32)` (the Merchant ORM default does this). Explicitly set `name`, `sms_sender`, and valid IANA `business_hours_tz`; verify the zone exists in both Python zoneinfo and Postgres pg_timezone_names. The default zone is **Australia/Sydney**, not the AWS region's timezone. `sms_sender` is the Realay `originator`: use a sender authorized on the Realay account for the destination country, not an arbitrary display label. Empty sender prevents a request; provider-specific sender validation must happen at onboarding.

Deliver the token once through an approved secure channel. Tokens are currently stored as plaintext unique values for webhook lookup: protect RDS, backups and operator access accordingly. Do not include them in tickets, logs, CSVs, URLs or frontend state. Rotate a merchant token transactionally and arrange a coordinated cutover; old tokens immediately stop authenticating. Keep REALAY_API_KEY separate from merchant tokens. The webhook is session-independent and requires merchant bearer auth, not a Google session.

Example **shape only**, with an intentionally non-live token and illustrative phone number (do not send this example to the real provider):

```http
POST /api/webhooks/communications HTTP/1.1
Host: comms.example.com
Authorization: Bearer EXAMPLE_ONLY_NOT_A_REAL_MERCHANT_TOKEN
Content-Type: application/json

{"job_id":"delivery-example-001","customer_name":"Example Customer","customer_phone":"+61412345678","delivery_day":"2026-10-06"}
```

All four fields must be nonempty strings without padding/control characters. Phone is E.164; date is a valid YYYY-MM-DD calendar date. `job_id` identifies a job **within its merchant**. First enqueue returns 202 with duplicate=false; identical replay returns 202 with duplicate=true; same ID with changed details returns 409. Missing/invalid auth is 401; malformed JSON 400; wrong content type 415; invalid field values/object shape **422 JSON**; oversized body 413; unavailable database 503. Retry ingestion with the **same** job_id after an ambiguous enqueue failure, not a newly generated ID. A 202 is queued acceptance, not evidence of SMS delivery.

CSV expected header:

```csv
job_id,customer_name,customer_phone,delivery_day
```

UTF-8 (optional BOM), exactly those four distinct columns; order can vary. Select the merchant in the protected operations page—no merchant token in CSV. Maximum one file, 2 MiB, 5,000 data rows. Same validation and merchant/job identity rules apply. Batches of 100 commit independently; invalid rows are reported and earlier committed batches remain queued if a later batch fails. Re-upload safely deduplicates matching rows; conflicting duplicates are row errors. The import runs in the active web session background, so a container restart may interrupt it; it is not a durable import queue.

## 8. Queue ordering, business hours and concurrency guarantees

The exact base ordered pending query is:

```sql
SELECT * FROM pending_comm WHERE status = 'pending' ORDER BY received_at ASC, id ASC;
```

`received_at` is receipt time; id breaks ties. Delivery day is an eligibility condition, **not** an ordering key. This inspection query is not a production claim and can be large; use a LIMIT for operational inspection. The worker additionally joins merchant, checks next_attempt_at, timezone validity and local eligibility, limits to one row and claims with **FOR UPDATE OF pending_comm SKIP LOCKED**. See ELIGIBILITY_SQL in app/release_worker.py for the actual predicates. Locked rows may be skipped, so concurrent completion order is not strictly FIFO.

Business hours are **Monday–Friday, 09:00 inclusive to 17:00 exclusive**, in each merchant's IANA timezone, using local dates and DST rules. Delivery day must be on or before the current local date. Overdue jobs stay eligible; weekend delivery dates wait until a weekday. There is no public-holiday calendar. The worker checks eligibility again immediately before the HTTP request. Keep host clocks synchronized and tzdata current.

A claim transaction records processing status, numbered attempt, unique claim token, incremented fencing version and a **300-second lease**, then commits before network I/O. Multiple scheduler processes can claim disjoint jobs through PostgreSQL row locks; normally run one unless throughput requires more. Web worker count cannot cause sends because only the separate scheduler sends. Multiple Reflex web workers need shared Redis session state (and appropriate sticky routing for long-lived WebSockets/background uploads); do not scale replicas with per-process in-memory session storage. Use the worker configuration supported by the installed Reflex/Granian version and verify state survives requests across workers before scaling. RDS remains the job system of record, not Redis.

Realay calls the real `https://api.realay.io/send/sms` with originator, recipient, reminder text and reference=job_id, a 30-second timeout, redirects disabled and no requests retry policy. Provider acceptance marks `sent`; **sent does not mean handset delivery**. A 2xx response not explicitly declaring rejection is treated as accepted, including non-JSON responses, matching current behavior.

Fencing protects database finalization, **not external exactly-once delivery**. A crash/timeout can occur after Realay accepted but before the database records success. Expired processing leases become failed/uncertain, never automatically requeued. Late results are retained on the attempt without overwriting a newer claim. `reference` is not assumed to be a provider-enforced idempotency key. Failed HTTP responses, transport errors and expired claims receive **no unconfirmed automatic retries**. Reconcile Realay records by reference/recipient/time, then use the existing acknowledged manual failed-job retry only when safe. If provider outcome is unknown, leave failed and investigate. Restoring a backup or replaying an old queue may resend previously delivered SMS—disable scheduler throughout restore/reconciliation.

## 9. Logs, monitoring, backups and incident operations

* **Backend/web:** container stdout/stderr via `docker logs --since 1h comms-web` (or the separately named backend/frontend containers), optionally shipped by the Docker logging driver/CloudWatch agent to a restricted log group. No application logfile path is assumed.
* **Scheduler:** `docker logs --since 1h comms-scheduler`; watch cycle counts, disabled-key errors, claim-expiry warnings and failures. Some error paths use app.secure_logging to mask known env secrets, merchant bearer tokens and credential URL fragments, but raw logging.exception calls remain in webhook, scheduler and operations handlers. These raw calls bypass that helper, so stdout/stderr and forwarded logs may contain exception details, sensitive values or customer data; secret redaction is not guaranteed. Restrict container and centralized log access to authorized operators, encrypt stored logs and limit retention. Redaction is defense-in-depth, not permission to log request bodies or all provider data. Third-party/server/DB logs need their own controls.
* **Job attempts:** `communication_log` in RDS and the protected job-details panel retain timestamps, HTTP status, redacted response/error and attempt identity. Responses may still contain customer PII; limit retention and access. They are not delivery receipts.
* **Ingress:** Caddy service stdout/journald (or configured access log destination), nginx access/error destinations, or ALB access logs in a restricted encrypted bucket. Never enable Authorization/cookie/request-body logging; sanitize OAuth query parameters.
* **RDS:** PostgreSQL logs in RDS console/CloudWatch export and CloudWatch metrics/Performance Insights as configured. Avoid statement/parameter logging containing webhook tokens and customer data. Monitor storage, connections, locks and slow queries. The status/delivery/received index may not fully cover the base receipt/id order; inspect plans at scale rather than changing schema during this rollout.

Alert on oldest eligible pending age, growing failed/expired counts, scheduler silence/nonzero exits, web 5xx, DB connection exhaustion, disk/log growth, certificate expiry and Realay account/quota errors. The scheduler's bounded cycles may require capacity adjustment as backlog grows; never compensate with unsafe retry automation.

Enable encrypted automated RDS backups and point-in-time recovery with an explicit retention/RPO/RTO; take a pre-release snapshot. Test restore into an isolated database regularly, with no active sending credential. Maintain encrypted independent exports if policy requires them. Back up reviewed source/release manifests and ingress configuration; secrets belong in the secret manager, not repo snapshots. Local Docker writable frontend caches are rebuildable, not database backups.

Patch EC2/Docker/base images and Python/frontend dependencies, enforce least privilege and MFA, rotate Realay/OIDC/database/merchant credentials, restrict operator accounts, retain audited deployment approvals and prune old images/logs safely. Stop scheduler before an incident restore or uncertain rollback; reconcile external sends before enabling it again. Do not automatically downgrade migrations. Establish customer-data retention/deletion policy while respecting the schema's restrictive foreign keys and attempt-history audit needs.

## 10. Release acceptance checklist

1. Run `python -m unittest app.test_communications app.test_operations` in a configured staging environment; the added webhook/logging tests mock database failures and make no Realay calls. No test results are claimed by this document.
2. Confirm reviewed image/tag/digest and successful migration head before startup.
3. Confirm TLS, backend ping, browser WebSocket and protected operations refresh.
4. Confirm Google production callback/origin registration and complete real operator sign-in; test excluded identities.
5. Confirm a missing REALAY_API_KEY prevents any scheduler claim/send, then supply the real key only after merchant sender and timezone review.
6. In staging verify invalid payload is 422, enqueue/deduplicate/conflict/auth responses remain correct, business-hour boundaries and concurrent claims behave as expected. Use approved test recipients for live SMS checks.
7. Verify redaction where applied, restricted log access and retention (including raw exception logs), log rotation/alerts and isolated backup restore. Keep scheduler disabled until all checks and delivery-outcome reconciliation are complete.
