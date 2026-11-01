"""Agent tools. Each one is a read-only HTTP call to core-svc; none of them touch a database."""

import json
from dataclasses import dataclass, field
from typing import Any

from app.integrations.core_svc import CoreSvc, CoreSvcError

MAX_WINDOW_MIN = 7 * 24 * 60


@dataclass
class ToolCall:
    name: str
    args: dict[str, Any]
    ok: bool
    error: str | None = None


@dataclass
class Toolbox:
    """Runs tools against core-svc, records every call and enforces the per-turn call limit."""

    core: CoreSvc
    max_calls: int = 8
    calls: list[ToolCall] = field(default_factory=list)

    async def run(self, name: str, args: dict[str, Any]) -> dict | list:
        if len(self.calls) >= self.max_calls:
            result: dict | list = {"error": f"tool call limit ({self.max_calls}) reached; answer now"}
            self.calls.append(ToolCall(name, args, ok=False, error=result["error"]))
            return result
        try:
            result = await getattr(self, name)(**args)
            self.calls.append(ToolCall(name, args, ok=True))
        except CoreSvcError as err:
            result = {"error": str(err), "status": err.status}
            self.calls.append(ToolCall(name, args, ok=False, error=str(err)))
        return result

    async def list_equipment(self) -> list[dict]:
        return await self.core.list_equipment()

    async def get_equipment(self, equipment: str) -> dict:
        return await self.core.get_equipment(equipment.strip().upper())

    async def get_telemetry_summary(self, equipment: str, window_minutes: int = 15) -> dict:
        minutes = max(1, min(int(window_minutes), MAX_WINDOW_MIN))
        return await self.core.telemetry_summary(equipment.strip().upper(), minutes * 60)

    async def get_operations(self, equipment: str, limit: int = 10) -> list[dict]:
        return await self.core.operations(equipment.strip().upper(), max(1, min(int(limit), 50)))


def as_text(result: dict | list) -> str:
    return json.dumps(result, separators=(",", ":"), default=str)
