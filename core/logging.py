"""Structured, one-line logging helpers.

Every side-effecting decision in the service is expected to emit a single
``key=value`` log line via :func:`log_action`, always including a ``dry_run``
field and any relevant identifiers so the loop can be audited from the logs.
"""

from __future__ import annotations

import logging
from typing import Any

_LOGGER_NAME = "aio_arr"


def configure_logging(level: str = "INFO") -> None:
    """Configure the root ``aio_arr`` logger with a concise one-line format.

    Calling this more than once replaces the handler so the configuration is
    idempotent (useful across reloads and tests).
    """
    logger = logging.getLogger(_LOGGER_NAME)
    numeric_level = getattr(logging, level.upper(), logging.INFO)
    logger.setLevel(numeric_level)

    handler = logging.StreamHandler()
    handler.setFormatter(
        logging.Formatter("%(asctime)s %(levelname)s %(name)s %(message)s")
    )

    # Replace any existing handlers so repeated configuration is idempotent.
    logger.handlers = [handler]
    logger.propagate = False


def get_logger(name: str | None = None) -> logging.Logger:
    """Return a child of the shared ``aio_arr`` logger."""
    if name:
        return logging.getLogger(f"{_LOGGER_NAME}.{name}")
    return logging.getLogger(_LOGGER_NAME)


def format_action(action: str, *, dry_run: bool, **ids: Any) -> str:
    """Render a single ``key=value`` action line.

    ``None`` identifiers are omitted so the line stays readable.
    """
    parts = [f"action={action}", f"dry_run={str(dry_run).lower()}"]
    for key, value in ids.items():
        if value is not None:
            parts.append(f"{key}={value}")
    return " ".join(parts)


def log_action(
    logger: logging.Logger, action: str, *, dry_run: bool, **ids: Any
) -> None:
    """Emit a structured one-line INFO record for an action."""
    logger.info(format_action(action, dry_run=dry_run, **ids))
