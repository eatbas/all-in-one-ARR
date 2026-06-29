"""Async Servarr API helper used by Findarr."""

from __future__ import annotations

from typing import Any

import httpx

from modules.findarr.models import Compatibility, SearchUnit


class FindarrClientError(RuntimeError):
    """Raised when a Sonarr/Radarr API request cannot be completed."""


def _command_payload(unit: SearchUnit) -> dict[str, Any]:
    """Build the Sonarr/Radarr command body for a grouped search unit."""
    if unit.command == "EpisodeSearch":
        return {"name": "EpisodeSearch", "episodeIds": list(unit.episode_ids)}
    if unit.command == "SeasonSearch":
        return {
            "name": "SeasonSearch",
            "seriesId": unit.series_id,
            "seasonNumber": unit.season_number,
        }
    if unit.command == "SeriesSearch":
        return {"name": "SeriesSearch", "seriesId": unit.series_id}
    return {"name": "MoviesSearch", "movieIds": list(unit.movie_ids)}


def parse_version(value: str) -> tuple[int, int, int]:
    """Parse a semantic-ish version into a comparable three-part tuple."""
    parts: list[int] = []
    for raw_part in value.split(".")[:3]:
        digits = ""
        for char in raw_part:
            if char.isdigit():
                digits += char
            else:
                break
        parts.append(int(digits or 0))
    while len(parts) < 3:
        parts.append(0)
    return tuple(parts)  # type: ignore[return-value]


def _normalise_app_name(value: str) -> str:
    """Return a comparable application name from a Servarr status payload."""
    return value.strip().lower().replace(" ", "")


class FindarrArrClient:
    """Small client for the Sonarr/Radarr endpoints Findarr needs."""

    def __init__(
        self,
        *,
        app: str,
        base_url: str,
        api_key: str,
        http_client: httpx.AsyncClient | None = None,
    ) -> None:
        self.app = app
        self.base_url = base_url.rstrip("/")
        self.api_key = api_key
        self._client = http_client or httpx.AsyncClient(timeout=30.0)

    @property
    def configured(self) -> bool:
        """Whether this client has enough connection data to make requests."""
        return bool(self.base_url and self.api_key)

    async def _request(self, method: str, path: str, **kwargs: Any) -> Any:
        if not self.configured:
            raise FindarrClientError(f"{self.app} connection is not configured")
        try:
            response = await self._client.request(
                method,
                f"{self.base_url}{path}",
                headers={"X-Api-Key": self.api_key},
                **kwargs,
            )
            response.raise_for_status()
        except httpx.HTTPError as exc:
            raise FindarrClientError(f"{self.app} API request failed: {exc}") from exc
        if not response.content:
            return None
        return response.json()

    async def system_status(self) -> dict[str, Any]:
        """Return `/api/v3/system/status`."""
        data = await self._request("GET", "/api/v3/system/status")
        if not isinstance(data, dict):
            raise FindarrClientError(f"{self.app} returned an invalid status payload")
        return data

    async def compatibility(self) -> Compatibility:
        """Return whether the connected app satisfies Findarr's version target."""
        status = await self.system_status()
        version = str(status.get("version") or "0.0.0")
        app_name = str(status.get("appName") or self.app)
        expected_name = self.app.capitalize()
        if _normalise_app_name(app_name) != self.app:
            return Compatibility(
                ok=False,
                app_name=app_name,
                version=version,
                detail=(
                    f"Connected service is {app_name}; Findarr expected "
                    f"{expected_name} for the configured {self.app} connection"
                ),
            )
        minimum = (4, 0, 0) if self.app == "sonarr" else (6, 0, 0)
        actual = parse_version(version)
        if actual < minimum:
            required = "4+" if self.app == "sonarr" else "6+"
            return Compatibility(
                ok=False,
                app_name=app_name,
                version=version,
                detail=f"{app_name} {version} is unsupported; Findarr requires {self.app.capitalize()} {required}",
            )
        return Compatibility(
            ok=True,
            app_name=app_name,
            version=version,
            detail=f"Connected to {app_name} {version}",
        )

    async def queue_size(self) -> int:
        """Return current download queue size."""
        data = await self._request("GET", "/api/v3/queue", params={"page": 1, "pageSize": 1})
        if isinstance(data, dict):
            return int(data.get("totalRecords", len(data.get("records", []))))
        if isinstance(data, list):
            return len(data)
        return 0

    async def wanted(self, kind: str) -> list[dict[str, Any]]:
        """Fetch every wanted page for `missing` or `cutoff`."""
        records: list[dict[str, Any]] = []
        page = 1
        page_size = 100
        while True:
            data = await self._request(
                "GET",
                f"/api/v3/wanted/{kind}",
                params={"page": page, "pageSize": page_size},
            )
            if isinstance(data, dict):
                page_records = data.get("records", [])
                if not isinstance(page_records, list):
                    raise FindarrClientError(f"{self.app} wanted payload has invalid records")
                records.extend([record for record in page_records if isinstance(record, dict)])
                total = int(data.get("totalRecords", len(records)))
                if len(records) >= total or not page_records:
                    break
            elif isinstance(data, list):
                records.extend([record for record in data if isinstance(record, dict)])
                break
            else:
                raise FindarrClientError(f"{self.app} wanted payload is invalid")
            page += 1
        return records

    async def trigger_search(self, unit: SearchUnit) -> None:
        """Trigger the Sonarr/Radarr search command for one grouped unit."""
        await self._request("POST", "/api/v3/command", json=_command_payload(unit))

    async def aclose(self) -> None:
        """Close the underlying HTTP client."""
        await self._client.aclose()
