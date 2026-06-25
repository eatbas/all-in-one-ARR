"""Tests for core.logging."""

from __future__ import annotations

import logging

from core.logging import (
    configure_logging,
    format_action,
    get_logger,
    log_action,
)


def test_configure_logging_sets_level_and_single_handler() -> None:
    configure_logging("DEBUG")
    logger = logging.getLogger("aio_arr")
    assert logger.level == logging.DEBUG
    assert len(logger.handlers) == 1
    # Idempotent: a second call replaces, not appends.
    configure_logging("INFO")
    assert len(logger.handlers) == 1
    assert logger.level == logging.INFO


def test_configure_logging_unknown_level_falls_back_to_info() -> None:
    configure_logging("NONSENSE")
    assert logging.getLogger("aio_arr").level == logging.INFO


def test_get_logger_named_and_root() -> None:
    assert get_logger("trakt").name == "aio_arr.trakt"
    assert get_logger().name == "aio_arr"


def test_format_action_omits_none_ids() -> None:
    line = format_action("remove", tmdb=5, tvdb=None, title="X")
    assert "action=remove" in line
    assert "tmdb=5" in line
    assert "tvdb" not in line
    assert "title=X" in line


def test_log_action_emits_info(capsys) -> None:
    # Configure inside the test so the StreamHandler binds to the captured
    # stderr (the aio_arr logger does not propagate to the root caplog handler).
    configure_logging("INFO")
    log_action(get_logger("test"), "requested", tmdb=10)
    captured = capsys.readouterr().err
    assert "action=requested" in captured
    assert "tmdb=10" in captured
