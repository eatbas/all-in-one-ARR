"""Tests for core.webhooks."""

from __future__ import annotations

from fastapi import FastAPI
from fastapi.testclient import TestClient

from core.webhooks import WebhookRegistry


def build_app(registry: WebhookRegistry) -> FastAPI:
    app = FastAPI()
    app.include_router(registry.router)
    return app


def test_registered_handler_invoked() -> None:
    registry = WebhookRegistry()
    received: list[dict] = []

    async def handler(payload: dict) -> None:
        received.append(payload)

    registry.register("arr", handler)
    client = TestClient(build_app(registry))
    resp = client.post("/webhook/arr", json={"eventType": "Download"})
    assert resp.status_code == 200
    assert received == [{"eventType": "Download"}]


def test_unknown_subpath_returns_404() -> None:
    registry = WebhookRegistry()
    client = TestClient(build_app(registry))
    resp = client.post("/webhook/missing", json={})
    assert resp.status_code == 404


def test_invalid_json_returns_400() -> None:
    registry = WebhookRegistry()
    client = TestClient(build_app(registry))
    resp = client.post(
        "/webhook/arr",
        content=b"{not json",
        headers={"Content-Type": "application/json"},
    )
    assert resp.status_code == 400


def test_handler_failure_still_returns_200() -> None:
    registry = WebhookRegistry()

    async def boom(payload: dict) -> None:
        raise RuntimeError("downstream failure")

    registry.register("arr", boom)
    client = TestClient(build_app(registry))
    resp = client.post("/webhook/arr", json={"eventType": "Download"})
    # Must not surface a 5xx to the arr connection.
    assert resp.status_code == 200


def test_empty_body_treated_as_empty_dict() -> None:
    registry = WebhookRegistry()
    seen: list[dict] = []

    async def handler(payload: dict) -> None:
        seen.append(payload)

    registry.register("arr", handler)
    client = TestClient(build_app(registry))
    resp = client.post("/webhook/arr", content=b"")
    assert resp.status_code == 200
    assert seen == [{}]
