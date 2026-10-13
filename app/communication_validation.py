import reflex as rx

import re
from datetime import date

COLUMNS = ("job_id", "customer_name", "customer_phone", "delivery_day")
PHONE_PATTERN = re.compile(r"\+[1-9][0-9]{1,14}\Z")
DATE_PATTERN = re.compile(r"[0-9]{4}-[0-9]{2}-[0-9]{2}\Z")


def validate_job(payload: dict) -> tuple[dict[str, str], date]:
    values: dict[str, str] = {}
    for field in COLUMNS:
        value = payload.get(field)
        if not isinstance(value, str) or not value.strip():
            raise ValueError(f"{field} must be a nonempty string")
        if value != value.strip() or any(
            ord(c) < 32 or ord(c) == 127 for c in value
        ):
            raise ValueError(
                f"{field} contains whitespace padding or control characters"
            )
        if len(value) > (32 if field == "customer_phone" else 255):
            raise ValueError(f"{field} is too long")
        values[field] = value
    if not PHONE_PATTERN.fullmatch(values["customer_phone"]):
        raise ValueError("customer_phone must be an E.164 number")
    try:
        if not DATE_PATTERN.fullmatch(values["delivery_day"]):
            raise ValueError("Invalid date format")
        delivery_day = date.fromisoformat(values.pop("delivery_day"))
    except ValueError:
        raise ValueError(
            "delivery_day must be a valid YYYY-MM-DD date"
        ) from None
    return values, delivery_day
