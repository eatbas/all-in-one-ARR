#!/usr/bin/env python3
"""Export the FastAPI OpenAPI schema without touching runtime state.

The application factory creates SQLite/settings/token/poster paths as part of
context construction. For schema generation those paths are redirected to a
temporary directory so this script is deterministic and does not write secrets or
test artefacts into ``data/``.
"""

from __future__ import annotations

import argparse
import json
import os
import sys
import tempfile
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
BACKEND = ROOT / "backend"


def _normalise_schema(value: Any) -> Any:
    """Return ``value`` with dictionaries sorted recursively for stable output."""
    if isinstance(value, dict):
        return {key: _normalise_schema(value[key]) for key in sorted(value)}
    if isinstance(value, list):
        return [_normalise_schema(item) for item in value]
    return value


def export_schema(output: Path) -> None:
    """Build the app and write its OpenAPI schema to ``output``."""
    sys.path.insert(0, str(BACKEND))
    with tempfile.TemporaryDirectory(prefix="aio-arr-openapi-") as tmp:
        temp_dir = Path(tmp)
        env_overrides = {
            "DB_PATH": str(temp_dir / "aio-arr.db"),
            "TOKEN_STORE_PATH": str(temp_dir / "trakt_tokens.json"),
            "SETTINGS_STORE_PATH": str(temp_dir / "app_settings.json"),
            "POSTER_CACHE_PATH": str(temp_dir / "posters"),
            "TRAKT_CLIENT_ID": "",
            "TRAKT_CLIENT_SECRET": "",
            "SEER_URL": "",
            "SEER_API_KEY": "",
            "SONARR_URL": "",
            "SONARR_API_KEY": "",
            "RADARR_URL": "",
            "RADARR_API_KEY": "",
            "TMDB_API_KEY": "",
            "OMDB_API_KEY": "",
            "SABNZBD_URL": "",
            "SABNZBD_API_KEY": "",
            "QBITTORRENT_URL": "",
            "QBITTORRENT_API_KEY": "",
        }
        previous = {key: os.environ.get(key) for key in env_overrides}
        os.environ.update(env_overrides)
        app = None
        try:
            from core.app import create_app

            app = create_app()
            schema = _normalise_schema(app.openapi())
        finally:
            if app is not None:
                app.state.ctx.db.close()
            for key, value in previous.items():
                if value is None:
                    os.environ.pop(key, None)
                else:
                    os.environ[key] = value

    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(schema, indent=2, ensure_ascii=False) + "\n")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--output",
        type=Path,
        default=ROOT / "schema" / "openapi.json",
        help="Path to write the OpenAPI JSON schema.",
    )
    args = parser.parse_args()
    export_schema(args.output)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
