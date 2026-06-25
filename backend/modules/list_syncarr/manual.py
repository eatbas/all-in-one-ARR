"""User-initiated removal actions for the list_syncarr module.

These back the dashboard's manual delete controls: removing a single tracked
item, or sweeping every Available item (a manual trigger of the reconcile job
that is no longer scheduled autonomously). Both reuse :func:`remove_tracked_item`
so the not-owned-by-``me`` skip is honoured.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from core.logging import get_logger
from modules.list_syncarr.removal import remove_tracked_item

if TYPE_CHECKING:  # pragma: no cover
    from core.context import AppContext

_log = get_logger("list_syncarr.manual")


async def remove_one(ctx: "AppContext", list_id: str, trakt_id: int) -> bool:
    """Remove a single tracked item from its Trakt list.

    Returns ``True`` when the item exists and removal was attempted, ``False``
    when no such item is tracked (so the caller can answer 404).
    """
    item = ctx.db.get_item(trakt_id=trakt_id, list_id=list_id)
    if item is None:
        _log.info("no tracked item to remove: list=%s trakt=%s", list_id, trakt_id)
        return False
    await remove_tracked_item(ctx, item, reason="manual")
    return True
