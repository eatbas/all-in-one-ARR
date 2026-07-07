"""Standalone connection test for SABnzbd and qBittorrent.

Reads the values from ``.env`` via the project's ``Settings`` class, then calls
each service's ``test_connection()`` and prints a masked summary. Run from the
``backend`` directory with the virtual environment active:

    cd backend
    python test_download_clients.py
"""

from __future__ import annotations

import asyncio
import sys
from pathlib import Path

# Allow running from inside backend/ without installing the package.
ROOT = Path(__file__).resolve().parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

# These imports must follow the sys.path bootstrap above, so E402 is expected.
from core.clients.qbittorrent import QbittorrentClient  # noqa: E402
from core.clients.sabnzbd import SabnzbdClient  # noqa: E402
from core.config import Settings  # noqa: E402


def mask(value: str) -> str:
    """Return a short masked representation of a secret."""
    if not value:
        return "<empty>"
    if len(value) <= 4:
        return "***"
    return value[:2] + "..." + value[-2:]


async def main() -> int:
    settings = Settings()
    exit_code = 0

    print("SABnzbd")
    print(f"  URL     : {settings.SABNZBD_URL or '<empty>'}")
    print(f"  API key : {mask(settings.SABNZBD_API_KEY)}")
    sab = SabnzbdClient(
        base_url=settings.SABNZBD_URL,
        api_key=settings.SABNZBD_API_KEY,
    )
    try:
        result = await sab.test_connection()
    finally:
        await sab.aclose()
    status = "OK" if result["ok"] else "FAIL"
    print(f"  Status  : {status} - {result['detail']}")
    if not result["ok"]:
        exit_code = 1

    print()
    print("qBittorrent")
    print(f"  URL      : {settings.QBITTORRENT_URL or '<empty>'}")
    print(f"  API key  : {mask(settings.QBITTORRENT_API_KEY)}")
    qbit = QbittorrentClient(
        base_url=settings.QBITTORRENT_URL,
        api_key=settings.QBITTORRENT_API_KEY,
    )
    try:
        result = await qbit.test_connection()
    finally:
        await qbit.aclose()
    status = "OK" if result["ok"] else "FAIL"
    print(f"  Status   : {status} - {result['detail']}")
    if not result["ok"]:
        exit_code = 1

    return exit_code


if __name__ == "__main__":
    try:
        sys.exit(asyncio.run(main()))
    except KeyboardInterrupt:
        sys.exit(130)
