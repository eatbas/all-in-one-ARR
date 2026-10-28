"""Read-only health checks over SABnzbd and Sonarr/Radarr download settings.

Cleanarr never changes these settings; it only reports values that make stuck
or malicious downloads more likely. A value that could not be read produces an
informational entry rather than a warning.
"""

from __future__ import annotations

from modules.cleanarr.models import ArrDownloadHandling, HealthWarning, SabConfig

# SABnzbd's "abort" value for both the unwanted-extension and encrypted-RAR actions.
SAB_ACTION_ABORT = 2
# Extensions SABnzbd's own unwanted list should always contain.
REQUIRED_UNWANTED_EXTENSIONS = (".exe", ".scr", ".lnk")

_APP_LABELS = {"sonarr": "Sonarr", "radarr": "Radarr"}


def _unknown(source: str, code: str, detail: str) -> HealthWarning:
    """Return an informational entry for a value that could not be read."""
    return HealthWarning(source=source, code=code, detail=detail, level="info")


def sab_warnings(config: SabConfig | None) -> list[HealthWarning]:
    """Return warnings about SABnzbd's unwanted-file and encrypted-RAR handling."""
    if config is None:
        return [
            HealthWarning(
                source="sabnzbd",
                code="sab_unreachable",
                detail="SABnzbd settings could not be read.",
            )
        ]
    warnings: list[HealthWarning] = []
    if config.unwanted_action is None:
        warnings.append(
            _unknown(
                "sabnzbd",
                "unwanted_action_unknown",
                "Could not read SABnzbd's action for unwanted extensions.",
            )
        )
    elif config.unwanted_action != SAB_ACTION_ABORT:
        warnings.append(
            HealthWarning(
                source="sabnzbd",
                code="unwanted_action_not_abort",
                detail="SABnzbd does not abort jobs containing unwanted extensions.",
            )
        )
    missing = [
        extension
        for extension in REQUIRED_UNWANTED_EXTENSIONS
        if extension not in config.unwanted_extensions
    ]
    if missing:
        warnings.append(
            HealthWarning(
                source="sabnzbd",
                code="unwanted_extensions_incomplete",
                detail=(
                    "SABnzbd's unwanted extensions list is missing "
                    f"{', '.join(missing)}."
                ),
            )
        )
    warnings.extend(_encrypted_rar_warnings(config.encrypted_rar_action))
    return warnings


def _encrypted_rar_warnings(action: int | None) -> list[HealthWarning]:
    """Return the encrypted-RAR entry, if any."""
    if action is None:
        return [
            _unknown(
                "sabnzbd",
                "encrypted_rar_unknown",
                "Could not read SABnzbd's action for encrypted RAR files.",
            )
        ]
    if action != SAB_ACTION_ABORT:
        return [
            HealthWarning(
                source="sabnzbd",
                code="encrypted_rar_not_abort",
                detail="SABnzbd does not abort jobs with encrypted RAR files.",
            )
        ]
    return []


def arr_warnings(app: str, handling: ArrDownloadHandling | None) -> list[HealthWarning]:
    """Return warnings about an Arr's failed-download handling."""
    label = _APP_LABELS.get(app, app)
    if handling is None:
        return [
            _unknown(
                app,
                "download_handling_unknown",
                f"Could not read {label}'s download handling settings.",
            )
        ]
    checks = (
        (
            handling.completed_handling,
            "completed_handling",
            "Completed download handling",
        ),
        (
            handling.redownload_failed,
            "redownload_failed",
            "Redownload failed downloads",
        ),
        (
            handling.remove_failed,
            "remove_failed",
            "Remove failed downloads on the SABnzbd client",
        ),
    )
    warnings: list[HealthWarning] = []
    for value, code, setting in checks:
        if value is None:
            warnings.append(
                _unknown(app, f"{code}_unknown", f"{label}: {setting} is unknown.")
            )
        elif not value:
            warnings.append(
                HealthWarning(
                    source=app, code=f"{code}_off", detail=f"{label}: {setting} is off."
                )
            )
    return warnings
