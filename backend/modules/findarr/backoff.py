"""Per-unit retry backoff for Findarr searches.

A unit that has just been searched waits ``base_hours`` (the "retry delay"
setting) before it may be searched again. Every consecutive search that finds
nothing doubles the wait — base, 2×, 4×, 8× … — up to :data:`MAX_BACKOFF_HOURS`
(or the base delay itself when that is configured higher). A search that grabs
a release resets the count, and a unit that leaves the wanted list is pruned, so
a stubborn item quietens down without starving fresh ones.
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

# Longest wait between searches of the same unit: 30 days.
MAX_BACKOFF_HOURS = 720

# Doubling stops long before this exponent matters; it only bounds the integer.
_MAX_EXPONENT = 16


def max_delay_hours(base_hours: int) -> int:
    """Return the longest delay the backoff will use for ``base_hours``."""
    return max(base_hours, MAX_BACKOFF_HOURS)


def delay_hours(attempts: int, base_hours: int) -> int:
    """Return the wait after ``attempts`` consecutive searches that found nothing.

    ``0`` (never searched or last search grabbed) and ``1`` both wait the base
    delay; each further no-result search doubles it, capped by
    :func:`max_delay_hours`.
    """
    exponent = min(max(attempts - 1, 0), _MAX_EXPONENT)
    return min(base_hours * 2**exponent, max_delay_hours(base_hours))


def next_eligible_at(searched_at: datetime, attempts: int, base_hours: int) -> str:
    """Return when a unit searched at ``searched_at`` may be searched again."""
    eligible = searched_at + timedelta(hours=delay_hours(attempts, base_hours))
    return eligible.astimezone(UTC).isoformat()


def parse_iso(value: str) -> datetime | None:
    """Parse a stored ISO-8601 timestamp as an aware UTC datetime, or ``None``."""
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return None
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=UTC)
    return parsed.astimezone(UTC)


def is_due(next_eligible: str | None, now: datetime) -> bool:
    """Whether a unit with ``next_eligible`` may be searched at ``now``.

    Rows written before the backoff existed carry no timestamp and are due; an
    unparseable timestamp is treated the same rather than locking the unit out.
    """
    if next_eligible is None:
        return True
    parsed = parse_iso(next_eligible)
    return parsed is None or parsed <= now
