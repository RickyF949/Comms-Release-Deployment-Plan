import reflex as rx

import logging
import os
import re
import threading
import traceback
from urllib.parse import quote, unquote, urlsplit


def redact(value: str, secrets: tuple[str, ...] = ()) -> str:
    environment_secrets = tuple(
        value
        for key, value in os.environ.items()
        if any(
            marker in key.upper()
            for marker in (
                "SECRET",
                "TOKEN",
                "PASSWORD",
                "API_KEY",
                "DB_URL",
                "DATABASE_URL",
            )
        )
    )
    sensitive = set((*secrets, *environment_secrets))
    for secret in environment_secrets:
        if "://" in secret:
            parsed = urlsplit(secret)
            sensitive.update(
                part for part in (parsed.username, parsed.password) if part
            )
    variants = set()
    for secret in sensitive:
        if secret:
            variants.update((secret, unquote(secret), quote(secret, safe="")))
    for secret in sorted(variants, key=len, reverse=True):
        value = value.replace(secret, "[REDACTED]")
    value = re.sub(
        r"(?i)([a-z][a-z0-9+.-]*://)[^\s/@]+(?::[^\s/@]*)?@",
        r"\1[REDACTED]@",
        value,
    )
    value = re.sub(r"(?i)(bearer\s+)[^\s\"',}]+", r"\1[REDACTED]", value)
    value = re.sub(
        r"(?i)((?:api[_-]?key|access[_-]?token|webhook[_-]?token|client[_-]?secret|password)[\"']?\s*[:=]\s*[\"']?)[^\s\"',}&]+",
        r"\1[REDACTED]",
        value,
    )
    return value


class RedactingFilter(logging.Filter):
    _comms_redacting_filter = True
    _local = threading.local()

    def filter(self, record: logging.LogRecord) -> bool:
        if getattr(self._local, "active", False):
            record.msg = "[REDACTED: recursive log suppressed]"
            record.args = ()
            record.exc_info = None
            record.exc_text = None
            record.stack_info = None
            return False

        self._local.active = True
        try:
            parts = [record.getMessage()]
            if record.exc_info:
                parts.append(
                    logging.Formatter().formatException(record.exc_info)
                )
            elif record.exc_text:
                parts.append(record.exc_text)
            if record.stack_info:
                parts.append(record.stack_info)
            record.msg = redact("\n".join(parts))
        except Exception:
            # Never log a sanitizer failure: that would recurse or expose its input.
            logging.exception("Unexpected error")
            record.msg = "[REDACTED: log sanitization failed]"
        finally:
            record.args = ()
            record.exc_info = None
            record.exc_text = None
            record.stack_info = None
            self._local.active = False
        return True


_root_logger = logging.getLogger()
if not any(
    getattr(existing, "_comms_redacting_filter", False)
    for existing in _root_logger.filters
):
    _root_logger.addFilter(RedactingFilter())


def log_failure(secrets: tuple[str, ...] = ()) -> None:
    e = redact(traceback.format_exc(), secrets)
    logging.exception(f"Error: {e}", exc_info=False)
