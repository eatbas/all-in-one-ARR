"""Small, shared integer-coercion helpers for untrusted JSON and settings values.

Servarr payloads and persisted settings arrive as loosely typed JSON, so several
features need the same "parse an int or fall back" logic. Keeping it here gives
one definition of the rules instead of a private copy per module.
"""

from __future__ import annotations

from typing import Any


def parse_int(value: Any) -> int | None:
    """Return ``value`` as an ``int``, or ``None`` when it is not numeric."""
    try:
        return int(value)
    except TypeError, ValueError:
        return None


def coerce_int(value: Any, default: int) -> int:
    """Return ``value`` as an ``int``, or ``default`` when it is not numeric."""
    parsed = parse_int(value)
    return default if parsed is None else parsed


def bounded_int(value: Any, *, default: int, minimum: int, maximum: int) -> int:
    """Return ``value`` as an ``int`` clamped to ``[minimum, maximum]``.

    Non-numeric values fall back to ``default``, which callers keep in range.
    """
    parsed = parse_int(value)
    if parsed is None:
        return default
    return max(minimum, min(parsed, maximum))
