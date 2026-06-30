"""Small shared time helpers used across the API routers.

Kept separate so routers (e.g. the dashboard ``core.api`` and the trending
``core.trending_api``) can share the derivation without one importing the other's
internals.
"""

from __future__ import annotations

from datetime import datetime, timedelta


def next_sync_at(last_synced_at: str | None, interval_minutes: int) -> str | None:
    """Derive the next scheduled run from the last run plus the interval.

    This approximates the scheduler's next fire time (the APScheduler 4 wrapper does
    not expose it); returns ``None`` when there has never been a run. ``last_synced_at``
    is always written by :func:`core.db.utcnow_iso` (valid ISO-8601), so
    ``fromisoformat`` cannot fail here.
    """
    if last_synced_at is None:
        return None
    last = datetime.fromisoformat(last_synced_at)
    return (last + timedelta(minutes=interval_minutes)).isoformat()
