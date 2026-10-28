"""Cleanarr engine: strike stuck usenet queue items and remove repeat offenders.

One gated run:

1. reads SABnzbd's config, history and queue (each may fail independently);
2. per enabled Arr, checks compatibility, reads the queue and strikes every
   failed import or failed download (an unreachable app is skipped and keeps
   its strikes);
3. removes items at ``max_strikes`` with blocklisting and a new search, within
   one ``max_removals_per_run`` budget (dry run only logs them, once);
4. runs the opt-in malware and orphan passes (:mod:`.file_passes`);
5. stores the health warnings and the run summary.
"""

from __future__ import annotations

import json
from contextlib import AsyncExitStack
from dataclasses import asdict
from typing import TYPE_CHECKING, Any

from core.app_metrics import record_cleanarr_run, update_cleanarr_health_warnings
from core.logging import get_logger
from core.timefmt import utcnow_iso
from modules.cleanarr import file_passes
from modules.cleanarr.client import CleanarrArrClient, CleanarrClientError, client_for
from modules.cleanarr.health import arr_warnings, sab_warnings
from modules.cleanarr.models import (
    AppRun,
    HealthWarning,
    RunSummary,
    SabState,
)
from modules.cleanarr.queue_cleaner import (
    DownloadDecision,
    app_decisions,
    apply_removals,
    first_message,
    short_detail,
    strike_app,
)

if TYPE_CHECKING:  # pragma: no cover
    from core.context import AppContext, SyncGate

_log = get_logger("cleanarr")

APPS = ("sonarr", "radarr")
_DISABLED_DETAIL = "Cleanarr is disabled"


def _run_result(status: str, detail: str, counts: dict[str, int] | None = None) -> dict:
    """Return the run-now / scheduled-run response payload."""
    return {"status": status, "detail": detail, "counts": counts or {}}


def _summary_detail(summary: RunSummary) -> str:
    """Return a one-line, human-readable summary of a run's counts."""
    labels = (
        ("struck", "struck"),
        ("removed", "removed"),
        ("would_remove", "would remove"),
        ("already_gone", "already gone"),
        ("remove_failed", "failed to remove"),
        ("malware_deleted", "malware deleted"),
        ("quarantined", "quarantined"),
        ("purged", "purged"),
        ("file_failures", "file errors"),
    )
    counts = summary.counts()
    parts = [f"{counts[key]} {label}" for key, label in labels if counts[key]]
    prefix = "Dry run: " if summary.dry_run else ""
    return prefix + (", ".join(parts) if parts else "nothing to clean")


class CleanarrService:
    """Owns Cleanarr runs and the read views for one app process."""

    def __init__(self, ctx: AppContext) -> None:
        self._ctx = ctx

    @property
    def gate(self) -> SyncGate:
        """The gate serialising scheduled and manual runs and the strike reset."""
        return self._ctx.cleanarr_gate

    # ---- settings ----

    def settings(self) -> dict[str, Any]:
        """Return the persisted Cleanarr settings."""
        return self._ctx.settings_store.cleanarr_settings()

    def update_settings(self, updates: dict[str, Any]) -> dict[str, Any]:
        """Persist settings updates and return the normalised settings."""
        settings = self._ctx.settings_store.update_cleanarr_settings(updates)
        self._ctx.db.add_activity(
            "Cleanarr settings saved", "Cleanarr settings updated"
        )
        return settings

    # ---- read views ----

    async def status(self) -> dict[str, Any]:
        """Return settings, the last run, connections, health and strike counts."""
        settings = self.settings()
        state = self._ctx.db.cleanarr_run_state()
        rows = self._ctx.db.cleanarr_strike_rows()
        last_run = None
        if "last_run_at" in state:
            last_run = {
                "at": state["last_run_at"],
                "status": state.get("last_run_status", ""),
                "detail": state.get("last_run_detail", ""),
            }
        return {
            "settings": settings,
            "enabled": settings["enabled"],
            "dry_run": settings["dry_run"],
            "running": self.gate.is_running(),
            "last_run": last_run,
            "connections": json.loads(state.get("connections", "[]")),
            "health": json.loads(state.get("health", "[]")),
            "strikes": {
                "sonarr": sum(1 for row in rows if row["app"] == "sonarr"),
                "radarr": sum(1 for row in rows if row["app"] == "radarr"),
                "failed_import": sum(
                    1 for row in rows if row["reason"] == "failed_import"
                ),
                "failed_download": sum(
                    1 for row in rows if row["reason"] == "failed_download"
                ),
            },
        }

    async def queue(self) -> dict[str, Any]:
        """Return one row per stuck download with its strikes (read without the gate).

        ``held`` explains, per app, why the read holds downloads (their rows
        are then never shown as about to be removed); ``errors`` lists apps
        whose queue could not be read.
        """
        settings = self.settings()
        sab = SabState.from_reads(
            config=None,
            history=await self._ctx.sabnzbd.history_jobs(),
            queue_names=None,
        )
        rows = self._ctx.db.cleanarr_strike_rows()
        strikes = {(row["app"], row["download_id"]): row for row in rows}
        items: list[dict[str, Any]] = []
        errors: dict[str, str] = {}
        held: dict[str, str] = {}
        for app in self._enabled_apps(settings):
            client = client_for(self._ctx, app)
            try:
                arr_queue = await client.read_queue()
            except CleanarrClientError as exc:
                errors[app] = short_detail(str(exc))
                continue
            finally:
                await client.aclose()
            plan = app_decisions(app, arr_queue, settings, sab, rows)
            if plan.held_detail is not None:
                held[app] = plan.held_detail
            items.extend(
                self._queue_entry(
                    decision, settings, strikes.get((app, decision.item.download_id))
                )
                for decision in plan.decisions
            )
        return {
            "items": items,
            "errors": errors,
            "held": held,
            "max_strikes": settings["max_strikes"],
            "dry_run": settings["dry_run"],
        }

    @staticmethod
    def _queue_entry(
        decision: DownloadDecision,
        settings: dict[str, Any],
        strike: dict[str, Any] | None,
    ) -> dict[str, Any]:
        """Return one Queue-tab row for a failing download.

        A held download (its strikes frozen) is never shown as about to be
        removed, and an undecidable ignore is shown as not ignored.
        """
        item = decision.item
        strikes = int(strike["strikes"]) if strike else 0
        return {
            "app": item.app,
            "queue_id": item.queue_id,
            "download_id": item.download_id,
            "title": item.title,
            "reason": decision.reason,
            "message": first_message(item),
            "strikes": strikes,
            "max_strikes": settings["max_strikes"],
            "would_remove": not decision.held
            and strikes >= int(settings["max_strikes"]),
            "ignored": bool(decision.ignored),
            "excluded": decision.excluded,
        }

    async def history(self) -> list[dict[str, Any]]:
        """Return recent history entries, newest first."""
        return self._ctx.db.cleanarr_history_rows()

    # ---- actions ----

    async def run_now(self) -> dict[str, Any]:
        """Run once now; raises ``SyncAlreadyRunning`` when a run is in progress."""
        if not self.settings()["enabled"]:
            return _run_result("skipped", _DISABLED_DETAIL)
        return await self.gate.try_run(self._run_unlocked)

    async def scheduled_run(self) -> dict[str, Any]:
        """Scheduled body; the caller holds the gate. Disabled is a silent no-op."""
        if not self.settings()["enabled"]:
            return _run_result("skipped", _DISABLED_DETAIL)
        return await self._run_unlocked()

    async def clear_strikes(self) -> dict[str, int]:
        """Delete every strike; raises ``SyncAlreadyRunning`` during a run."""

        async def clear() -> dict[str, int]:
            count = self._ctx.db.cleanarr_clear_all_strikes()
            self._ctx.db.add_activity(
                "Cleanarr strikes cleared", f"Cleared {count} strike(s)."
            )
            return {"count": count}

        return await self.gate.try_run(clear)

    async def ignore(self, download_id: str) -> dict[str, Any]:
        """Add a download id to the ignore list and drop its strikes.

        Runs under the gate, so it raises ``SyncAlreadyRunning`` while a run is
        in progress: an acknowledged Ignore can never be followed by a removal
        decided from an older run's settings. A full ignore list raises
        ``CleanarrIgnoreListFull`` before anything changes.
        """

        async def add() -> dict[str, Any]:
            store = self._ctx.settings_store
            settings = store.cleanarr_add_ignored_download(download_id)
            for app in APPS:
                self._ctx.db.cleanarr_delete_strike(app, download_id)
            self._ctx.db.add_activity("Cleanarr download ignored", download_id)
            return settings

        return await self.gate.try_run(add)

    # ---- the run ----

    async def _run_unlocked(self) -> dict[str, Any]:
        """Run every enabled step once. The caller must hold the gate."""
        try:
            return await self._run_steps()
        except Exception as exc:
            self._record_run_state("error", short_detail(f"Run failed: {exc}"))
            record_cleanarr_run(status="error")
            _log.exception("Cleanarr run failed")
            raise

    async def _run_steps(self) -> dict[str, Any]:
        """Compose the run; Arr clients stay open until the removals are done."""
        settings = self.settings()
        summary = RunSummary(dry_run=bool(settings["dry_run"]))
        sab = await self._load_sab_state()
        async with AsyncExitStack() as stack:
            runs: list[AppRun] = []
            clients: dict[str, CleanarrArrClient] = {}
            for app in self._enabled_apps(settings):
                client = client_for(self._ctx, app)
                stack.push_async_callback(client.aclose)
                clients[app] = client
                runs.append(await self._run_app(client, settings, sab, summary))
            await apply_removals(self._ctx.db, clients, runs, settings, summary)
        db = self._ctx.db
        await file_passes.malware_pass(db, settings, sab, runs, summary)
        await file_passes.orphan_pass(db, settings, sab, runs, summary)
        self._health_pass(sab, runs, summary)
        detail = _summary_detail(summary)
        self._record_run_state("completed", detail)
        record_cleanarr_run(status="completed")
        if summary.changed():
            db.add_activity("Cleanarr", detail)
        return _run_result("completed", detail, summary.counts())

    @staticmethod
    def _enabled_apps(settings: dict[str, Any]) -> list[str]:
        """Return the apps whose ``apps.<app>.enabled`` switch is on."""
        return [app for app in APPS if settings["apps"][app]["enabled"]]

    async def _load_sab_state(self) -> SabState:
        """Read SABnzbd's config, history and queue names (each may be ``None``)."""
        sabnzbd = self._ctx.sabnzbd
        config = await sabnzbd.get_config()
        history = await sabnzbd.history_jobs()
        queue_names = await sabnzbd.queue_filenames()
        return SabState.from_reads(
            config=config, history=history, queue_names=queue_names
        )

    async def _run_app(
        self,
        client: CleanarrArrClient,
        settings: dict[str, Any],
        sab: SabState,
        summary: RunSummary,
    ) -> AppRun:
        """Gate one app, read its queue and update its strikes.

        A failed compatibility check or queue read skips the app without
        touching its strikes.
        """
        try:
            compatibility = await client.compatibility()
            if not compatibility.ok:
                return AppRun(app=client.app, ok=False, detail=compatibility.detail)
            arr_queue = await client.read_queue()
        except CleanarrClientError as exc:
            return AppRun(app=client.app, ok=False, detail=short_detail(str(exc)))
        try:
            handling = await client.download_handling()
        except CleanarrClientError:
            handling = None
        run = AppRun(
            app=client.app,
            ok=True,
            detail=compatibility.detail,
            items=arr_queue.items,
            unparsed_output_paths=arr_queue.unparsed_output_paths,
            references_complete=arr_queue.references_complete,
            downloads_complete=arr_queue.downloads_complete,
            handling=handling,
        )
        if settings["queue"]["enabled"]:
            run.struck = strike_app(self._ctx.db, run, settings, sab, summary)
        return run

    def _health_pass(
        self, sab: SabState, runs: list[AppRun], summary: RunSummary
    ) -> None:
        """Store connections and health warnings, and update the gauge."""
        warnings: list[HealthWarning] = sab_warnings(sab.config)
        connections = [
            {
                "app": "sabnzbd",
                "ok": sab.reachable,
                "detail": "Connected to SABnzbd"
                if sab.reachable
                else "SABnzbd settings or history could not be read.",
            }
        ]
        for run in runs:
            connections.append({"app": run.app, "ok": run.ok, "detail": run.detail})
            if run.ok:
                warnings.extend(arr_warnings(run.app, run.handling))
            else:
                warnings.append(
                    HealthWarning(
                        source=run.app,
                        code="app_skipped",
                        detail=f"Skipped last run: {run.detail}. Strikes left unchanged.",
                    )
                )
        warnings.extend(summary.notes)
        db = self._ctx.db
        db.cleanarr_set_run_state("connections", json.dumps(connections))
        db.cleanarr_set_run_state(
            "health", json.dumps([asdict(warning) for warning in warnings])
        )
        update_cleanarr_health_warnings(
            sum(1 for warning in warnings if warning.level == "warning")
        )

    def _record_run_state(self, status: str, detail: str) -> None:
        """Persist the last run's time, status and detail."""
        db = self._ctx.db
        db.cleanarr_set_run_state("last_run_at", utcnow_iso())
        db.cleanarr_set_run_state("last_run_status", status)
        db.cleanarr_set_run_state("last_run_detail", detail)
