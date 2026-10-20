"""Languagarr replacement-search worker: send bounded, re-validated searches.

Every queued row is re-checked against Sonarr immediately before its search, so
the queue never spends an indexer search on a file that was replaced, fixed or
removed, on a series that left the configured scope or was unmonitored, or (with
``monitored_only``) on an episode the user unmonitored after it was queued.
Sonarr runs API-triggered searches as user-invoked, so this re-check is the only
thing standing between a stale row and a replacement the user did not want.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

from core.app_metrics import record_languagarr_searches
from core.audio_languages import describe_languages
from core.coerce import coerce_int
from modules.languagarr.audio import file_audio_verdict
from modules.languagarr.client import LanguagarrClientError, LanguagarrSonarrClient
from modules.languagarr.models import Scope

if TYPE_CHECKING:  # pragma: no cover
    from core.context import AppContext


def run_result(
    status: str, *, searched: int = 0, failed: int = 0, resolved: int = 0
) -> dict[str, Any]:
    """Return the worker / run-now response payload."""
    return {
        "status": status,
        "searched": searched,
        "failed": failed,
        "resolved": resolved,
    }


async def searchable_episode_ids(
    client: LanguagarrSonarrClient, row: dict[str, Any], scope: Scope
) -> list[int]:
    """Return the queued episode ids still worth searching; ``[]`` means resolved.

    A row is resolved when its file no longer exists or is now compliant, when
    its series no longer exists or is out of scope (profile or monitoring), or —
    with ``monitored_only`` — when none of its queued episodes is still a
    monitored episode of that file.
    """
    file_id = int(row["episode_file_id"])
    fresh = await client.episode_file(file_id)
    if fresh is None:
        return []
    verdict, _ = file_audio_verdict(fresh, scope.languages)
    if verdict.compliant:
        return []
    series = await client.series_by_id(int(row["series_id"]))
    if series is None or not scope.includes(series):
        return []
    queued = [int(episode_id) for episode_id in row["episode_ids"]]
    if not scope.monitored_only:
        return queued
    monitored = {
        coerce_int(episode.get("id"), 0)
        for episode in await client.episodes_for_file(file_id)
        if bool(episode.get("monitored", True))
    }
    return [episode_id for episode_id in queued if episode_id in monitored]


async def process_rows(
    ctx: AppContext,
    client: LanguagarrSonarrClient,
    rows: list[dict[str, Any]],
    scope: Scope,
) -> dict[str, Any]:
    """Re-validate and search each pending row; resolved rows leave the queue."""
    searched = failed = resolved = 0
    for row in rows:
        file_id = int(row["episode_file_id"])
        try:
            episode_ids = await searchable_episode_ids(client, row, scope)
            if not episode_ids:
                resolved += 1
                ctx.db.languagarr_delete_row(file_id)
                continue
            await client.episode_search(episode_ids)
        except LanguagarrClientError as exc:
            failed += 1
            ctx.db.languagarr_mark_attempt(file_id, error=str(exc))
            continue
        searched += 1
        ctx.db.languagarr_mark_attempt(file_id)
    record_languagarr_searches(succeeded=searched, failed=failed)
    ctx.db.add_activity(
        "Languagarr searches sent",
        f"Sent {searched} replacement search(es) for "
        f"{describe_languages(scope.languages)} audio"
        + (f"; {failed} failed" if failed else "")
        + (f"; {resolved} already resolved" if resolved else "")
        + ".",
    )
    return run_result("completed", searched=searched, failed=failed, resolved=resolved)
