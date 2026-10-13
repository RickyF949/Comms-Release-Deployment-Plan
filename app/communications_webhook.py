import reflex as rx

import json
from datetime import date
from secrets import compare_digest

from sqlalchemy import select
from sqlalchemy.dialects.postgresql import insert
from starlette.requests import Request
from starlette.responses import JSONResponse
from starlette.concurrency import run_in_threadpool

from app.models import Merchant, PendingComm
from app.secure_logging import log_failure
from app.communication_validation import validate_job

import logging


MAX_BODY_BYTES = 16384


def error_response(message: str, status: int) -> JSONResponse:
    headers = {"Cache-Control": "no-store"}
    if status == 401:
        headers["WWW-Authenticate"] = "Bearer"
    return JSONResponse(
        {"error": str(message)}, status_code=status, headers=headers
    )


def enqueue(
    token: str, values: dict[str, str], delivery_day: date
) -> JSONResponse:
    try:
        with rx.session() as session:
            merchant = session.scalars(
                select(Merchant).where(Merchant.webhook_token == token).limit(1)
            ).first()
            if merchant is None or not compare_digest(
                merchant.webhook_token, token
            ):
                return error_response("Invalid merchant authorization", 401)
            inserted = session.execute(
                insert(PendingComm)
                .values(
                    merchant_id=merchant.id, delivery_day=delivery_day, **values
                )
                .on_conflict_do_nothing(
                    constraint="uq_pending_comm_merchant_job"
                )
                .returning(PendingComm.id)
            ).scalar_one_or_none()
            existing = session.scalars(
                select(PendingComm)
                .where(
                    PendingComm.merchant_id == merchant.id,
                    PendingComm.job_id == values["job_id"],
                )
                .limit(1)
            ).one()
            if inserted is None and (
                existing.customer_name != values["customer_name"]
                or existing.customer_phone != values["customer_phone"]
                or existing.delivery_day != delivery_day
            ):
                return error_response(
                    "job_id already exists with different job details", 409
                )
            result = {
                "job_id": existing.job_id,
                "status": existing.status,
                "duplicate": inserted is None,
            }
            session.commit()
        return JSONResponse(
            result, status_code=202, headers={"Cache-Control": "no-store"}
        )
    except Exception:
        logging.exception("Unexpected error")
        log_failure((token,))
        return error_response(
            "Queue unavailable; retry the same job_id later", 503
        )


async def communications_webhook(request: Request) -> JSONResponse:
    authorization = request.headers.get("authorization", "")
    parts = authorization.split()
    if (
        len(parts) != 2
        or parts[0].lower() != "bearer"
        or not 1 <= len(parts[1]) <= 128
    ):
        return error_response("Merchant bearer authorization is required", 401)
    token = parts[1]
    if (
        request.headers.get("content-type", "").split(";", 1)[0].strip().lower()
        != "application/json"
    ):
        return error_response("Content-Type must be application/json", 415)
    try:
        body = bytearray()
        async for chunk in request.stream():
            body.extend(chunk)
            if len(body) > MAX_BODY_BYTES:
                return error_response("Request body too large", 413)
        payload = json.loads(body)
    except (ValueError, UnicodeError):
        logging.exception("Unexpected error")
        return error_response("Malformed JSON", 400)
    except Exception:
        logging.exception("Unexpected error")
        log_failure((token,))
        return error_response("Unable to read request body", 400)
    if not isinstance(payload, dict):
        return error_response("JSON body must be an object", 422)
    try:
        values, delivery_day = validate_job(payload)
    except ValueError as e:
        return error_response(e, 422)
    return await run_in_threadpool(enqueue, token, values, delivery_day)
