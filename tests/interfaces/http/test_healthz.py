"""Smoke test for the /healthz route."""

from __future__ import annotations

from httpx import AsyncClient


async def test_healthz_returns_ok(http_client: AsyncClient) -> None:
    response = await http_client.get("/healthz")
    assert response.status_code == 200
    assert response.json() == {"status": "ok"}
