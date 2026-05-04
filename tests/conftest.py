"""Shared pytest fixtures."""

from __future__ import annotations

from collections.abc import AsyncGenerator

import pytest
from httpx import ASGITransport, AsyncClient

from app.interfaces.http.app import app as fastapi_app


@pytest.fixture(autouse=True)
def _no_notify(monkeypatch: pytest.MonkeyPatch) -> None:
    """Silence desktop notifications during tests · prevents notify-send spam."""
    monkeypatch.setenv("WIKI_TRANSLATOR_NO_NOTIFY", "1")


@pytest.fixture
async def http_client() -> AsyncGenerator[AsyncClient]:
    """Async HTTP client wired to the FastAPI app via ASGI transport (no socket)."""
    transport = ASGITransport(app=fastapi_app)
    async with AsyncClient(transport=transport, base_url="http://testserver") as client:
        yield client
