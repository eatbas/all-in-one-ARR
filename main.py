"""Entrypoint: ``uvicorn main:app``.

All wiring lives in :mod:`core.app`; this module only exposes ``app`` and a
convenience ``__main__`` runner.
"""

from __future__ import annotations

from core.app import create_app

app = create_app()


if __name__ == "__main__":  # pragma: no cover
    import uvicorn

    from core.config import Settings

    settings = Settings()
    uvicorn.run(app, host="0.0.0.0", port=settings.WEBHOOK_PORT)
