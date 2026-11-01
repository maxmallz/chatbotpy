"""Offline agent and harness against a mocked core-svc."""

import httpx
import pytest
import respx

from app.agent import harness
from app.agent.harness import HistoryMessage, _messages, run_turn
from app.config import get_settings
from app.integrations.core_svc import CoreSvc

BASE = "http://core-svc.test"

EQUIPMENT = [{"tag": "PUMP-01", "name": "Cooling water pump 1", "station": "STATION-1", "status": "Faulted"}]
DETAIL = {**EQUIPMENT[0], "assets": [], "channels": [], "last_operation": None}
SUMMARY = {
    "equipment": "PUMP-01", "status": "Faulted", "window_s": 900,
    "tags": [{
        "tag": "vibration", "unit": "mm/s", "lo_limit": 0.0, "hi_limit": 7.1, "samples": 120,
        "min": 2.0, "max": 9.0, "avg": 5.5, "last": 9.0, "last_ts": "2026-10-31T20:00:00Z",
        "slope_per_min": 3.5, "trend": "rising", "out_of_limit": 33, "last_out_of_limit": True,
    }],
}
OPS = [{"id": 3, "equipment": "PUMP-01", "op": "fault", "params": {"kind": "cavitation"},
        "actor": "factoryctl", "ts": "2026-10-31T20:00:00+00:00"}]


@pytest.fixture(autouse=True)
def offline(monkeypatch):
    monkeypatch.setenv("AGENT_MODEL", "offline")
    get_settings.cache_clear()
    yield
    get_settings.cache_clear()


def mock_core(router: respx.Router) -> None:
    router.get(f"{BASE}/equipment").respond(json=EQUIPMENT)
    router.get(f"{BASE}/equipment/PUMP-01").respond(json=DETAIL)
    router.get(f"{BASE}/equipment/PUMP-01/telemetry/summary").respond(json=SUMMARY)
    router.get(f"{BASE}/equipment/PUMP-01/operations").respond(json=OPS)
    router.get(f"{BASE}/equipment/NOPE-9").respond(404, json={"error": "not found"})


@respx.mock
async def test_offline_reports_rising_vibration():
    mock_core(respx.mock)
    reply = await run_turn([], "How is pump-01 doing?", core=CoreSvc(base_url=BASE))
    assert reply.model == "offline"
    assert "PUMP-01" in reply.text and "Faulted" in reply.text
    assert "vibration" in reply.text and "rising" in reply.text and "OUTSIDE" in reply.text
    names = [c["name"] for c in reply.tools_used]
    assert names == ["list_equipment", "get_equipment", "get_telemetry_summary", "get_operations"]
    assert all(c["ok"] for c in reply.tools_used)


@respx.mock
async def test_offline_unknown_equipment():
    mock_core(respx.mock)
    reply = await run_turn([], "status of NOPE-9", core=CoreSvc(base_url=BASE))
    assert "couldn't find NOPE-9" in reply.text
    assert reply.tools_used[-1]["ok"] is False


@respx.mock
async def test_core_svc_down():
    respx.mock.get(f"{BASE}/equipment").mock(side_effect=httpx.ConnectError("refused"))
    reply = await run_turn([], "status of PUMP-01", core=CoreSvc(base_url=BASE))
    assert "couldn't reach core-svc" in reply.text


async def test_tool_call_limit(monkeypatch):
    monkeypatch.setenv("AGENT_MAX_TOOL_CALLS", "1")
    get_settings.cache_clear()
    with respx.mock:
        mock_core(respx.mock)
        reply = await run_turn([], "status of PUMP-01", core=CoreSvc(base_url=BASE))
    assert [c["ok"] for c in reply.tools_used] == [True, False]
    assert "limit" in reply.tools_used[1]["error"]


def test_messages_alternate_and_end_with_user():
    history = [
        HistoryMessage("assistant", "hello"),  # dropped: must start with a user turn
        HistoryMessage("user", "a"),
        HistoryMessage("user", "b"),
        HistoryMessage("assistant", "c"),
    ]
    msgs = _messages(history, "d")
    assert [m["role"] for m in msgs] == ["user", "assistant", "user"]
    assert msgs[0]["content"] == "a\n\nb" and msgs[-1]["content"] == "d"


def test_claude_tools_have_schemas():
    tools = harness._claude_tools(harness.Toolbox(core=None))  # type: ignore[arg-type]
    names = sorted(t.name for t in tools)
    assert names == ["get_equipment", "get_operations", "get_telemetry_summary", "list_equipment"]
