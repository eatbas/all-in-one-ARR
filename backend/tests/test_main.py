"""Tests for the main entrypoint."""

from __future__ import annotations


def test_main_exposes_app(monkeypatch, tmp_path) -> None:
    # create_app() now builds the context at import time, so provide config.
    monkeypatch.setenv("TRAKT_CLIENT_ID", "cid")
    monkeypatch.setenv("TRAKT_CLIENT_SECRET", "secret")
    monkeypatch.setenv("SEER_URL", "http://js:5055")
    monkeypatch.setenv("SEER_API_KEY", "key")
    monkeypatch.setenv("DB_PATH", str(tmp_path / "db.sqlite"))
    monkeypatch.setenv("TOKEN_STORE_PATH", str(tmp_path / "tok.json"))

    import main

    assert main.app.title == "All-in-One ARR"
    # create_app() eagerly built a context holding a real SQLite connection;
    # close it so it is not left open for interpreter-shutdown GC.
    main.app.state.ctx.db.close()
