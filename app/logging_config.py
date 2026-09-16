from __future__ import annotations

import logging
import os
import re
import sys

from contextvars import ContextVar
from logging.handlers import RotatingFileHandler
from pathlib import Path


APP_LOGGER_NAME = "hackdex"

LOG_DIR = Path(
    os.getenv(
        "HACKDEX_LOG_DIR",
        "/data/logs",
    )
)

LOG_FILE = LOG_DIR / "hackdex-manager.log"

DEFAULT_LOG_LEVEL = "INFO"

MAX_LOG_BYTES = 10 * 1024 * 1024

BACKUP_COUNT = 5


VALID_LOG_LEVELS = {
    "DEBUG",
    "INFO",
    "WARNING",
    "ERROR",
    "CRITICAL",
}


_request_id = ContextVar(
    "hackdex_request_id",
    default=None,
)


_SECRET_PATTERNS = [
    re.compile(
        r'(?i)'
        r'('
        r'authorization'
        r'|api[_-]?key'
        r'|access[_-]?token'
        r'|refresh[_-]?token'
        r'|token'
        r'|password'
        r'|secret'
        r')'
        r'(\s*[:=]\s*)'
        r'([^\s,;]+)'
    ),
    re.compile(
        r'(?i)'
        r'(bearer\s+)'
        r'([A-Za-z0-9._~+/=-]+)'
    ),
]


class RequestContextFilter(logging.Filter):

    def filter(
        self,
        record: logging.LogRecord,
    ) -> bool:

        request_id = _request_id.get()

        if (
            request_id
            and not getattr(
                record,
                "_hackdex_request_tagged",
                False,
            )
        ):
            try:
                message = record.getMessage()

                record.msg = (
                    f"[req={request_id}] "
                    f"{message}"
                )

                record.args = ()

                record._hackdex_request_tagged = True

            except Exception:
                pass

        return True


class SecretRedactionFilter(logging.Filter):

    def filter(
        self,
        record: logging.LogRecord,
    ) -> bool:

        try:
            message = record.getMessage()

            for pattern in _SECRET_PATTERNS:

                if pattern.groups >= 3:
                    message = pattern.sub(
                        r'\1\2[REDACTED]',
                        message,
                    )

                else:
                    message = pattern.sub(
                        r'\1[REDACTED]',
                        message,
                    )

            record.msg = message
            record.args = ()

        except Exception:
            # Logging must never break the application.
            pass

        return True


def _resolve_level_name() -> str:

    requested = str(
        os.getenv(
            "LOG_LEVEL",
            DEFAULT_LOG_LEVEL,
        )
    ).upper().strip()

    if requested not in VALID_LOG_LEVELS:
        return DEFAULT_LOG_LEVEL

    return requested


def _resolve_level() -> int:

    return getattr(
        logging,
        _resolve_level_name(),
        logging.INFO,
    )


def configure_logging() -> logging.Logger:

    logger = logging.getLogger(
        APP_LOGGER_NAME
    )

    if getattr(
        logger,
        "_hackdex_configured",
        False,
    ):
        return logger

    level = _resolve_level()

    logger.setLevel(level)
    logger.propagate = False

    formatter = logging.Formatter(
        fmt=(
            "%(asctime)s | "
            "%(levelname)-8s | "
            "%(name)s | "
            "%(message)s"
        ),
        datefmt="%Y-%m-%d %H:%M:%S",
    )

    context_filter = (
        RequestContextFilter()
    )

    redaction_filter = (
        SecretRedactionFilter()
    )


    console_handler = logging.StreamHandler(
        sys.stdout
    )

    console_handler.setLevel(level)

    console_handler.setFormatter(
        formatter
    )

    console_handler.addFilter(
        context_filter
    )

    console_handler.addFilter(
        redaction_filter
    )

    logger.addHandler(
        console_handler
    )


    try:

        LOG_DIR.mkdir(
            parents=True,
            exist_ok=True,
        )

        file_handler = RotatingFileHandler(
            LOG_FILE,
            maxBytes=MAX_LOG_BYTES,
            backupCount=BACKUP_COUNT,
            encoding="utf-8",
        )

        file_handler.setLevel(level)

        file_handler.setFormatter(
            formatter
        )

        file_handler.addFilter(
            context_filter
        )

        file_handler.addFilter(
            redaction_filter
        )

        logger.addHandler(
            file_handler
        )

    except Exception as exc:

        logger.error(
            "Unable to initialize persistent "
            "file logging at %s: %s",
            LOG_FILE,
            exc,
        )


    logger._hackdex_configured = True

    logger.info(
        "Logging initialized "
        "level=%s file=%s "
        "rotation_bytes=%s backups=%s",
        logging.getLevelName(level),
        LOG_FILE,
        MAX_LOG_BYTES,
        BACKUP_COUNT,
    )

    return logger


def get_logger(
    component: str | None = None,
) -> logging.Logger:

    configure_logging()

    if not component:
        return logging.getLogger(
            APP_LOGGER_NAME
        )

    cleaned = (
        str(component)
        .strip()
        .replace(" ", "_")
    )

    return logging.getLogger(
        f"{APP_LOGGER_NAME}.{cleaned}"
    )


def current_log_level() -> str:

    logger = configure_logging()

    return logging.getLevelName(
        logger.level
    )


def startup_log_level() -> str:

    return _resolve_level_name()


def set_log_level(
    level: str,
) -> str:

    requested = str(
        level or ""
    ).upper().strip()

    if requested not in VALID_LOG_LEVELS:
        raise ValueError(
            "Invalid log level. "
            "Use DEBUG, INFO, WARNING, "
            "ERROR, or CRITICAL."
        )

    numeric_level = getattr(
        logging,
        requested,
    )

    logger = configure_logging()

    logger.setLevel(
        numeric_level
    )

    for handler in logger.handlers:
        handler.setLevel(
            numeric_level
        )

    return requested


def set_request_id(
    request_id: str,
):

    return _request_id.set(
        request_id
    )


def reset_request_id(
    token,
) -> None:

    _request_id.reset(
        token
    )


def current_request_id() -> str | None:

    return _request_id.get()


def current_log_file() -> str:

    return str(LOG_FILE)
