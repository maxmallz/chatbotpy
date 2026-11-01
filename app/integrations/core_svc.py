"""HTTP client for nest core-svc, the only data source chatbotpy uses."""

from typing import Any

import httpx

from app.config import get_settings


class CoreSvcError(Exception):
    def __init__(self, status: int, message: str):
        super().__init__(message)
        self.status = status


class CoreSvc:
    def __init__(self, base_url: str | None = None, timeout_s: float | None = None,
                 transport: httpx.AsyncBaseTransport | None = None):
        s = get_settings()
        self._client = httpx.AsyncClient(
            base_url=base_url or s.core_svc_url,
            timeout=timeout_s or s.core_svc_timeout_s,
            transport=transport,
        )

    async def aclose(self) -> None:
        await self._client.aclose()

    async def _get(self, path: str, **params: Any) -> Any:
        params = {k: v for k, v in params.items() if v is not None}
        try:
            r = await self._client.get(path, params=params)
        except httpx.HTTPError as err:
            raise CoreSvcError(503, f"core-svc unreachable: {err}") from err
        if r.status_code >= 400:
            try:
                message = r.json().get("error", r.text)
            except ValueError:
                message = r.text
            raise CoreSvcError(r.status_code, message)
        return r.json()

    async def health(self) -> dict:
        try:
            r = await self._client.get("/health")
            return r.json()
        except (httpx.HTTPError, ValueError) as err:
            return {"status": "down", "error": str(err)}

    async def list_equipment(self) -> list[dict]:
        return await self._get("/equipment")

    async def get_equipment(self, tag: str) -> dict:
        return await self._get(f"/equipment/{tag}")

    async def telemetry_summary(self, tag: str, window_s: int) -> dict:
        return await self._get(f"/equipment/{tag}/telemetry/summary", window=window_s)

    async def operations(self, tag: str, limit: int) -> list[dict]:
        return await self._get(f"/equipment/{tag}/operations", limit=limit)
