"""run_turn(): the only code that runs the agent. Stateless: the caller sends the history."""

import asyncio
import re
from dataclasses import asdict, dataclass
from typing import Literal

import anthropic
from anthropic import beta_async_tool

from app.agent.tools import Toolbox, as_text
from app.config import get_settings
from app.integrations.core_svc import CoreSvc, CoreSvcError

SYSTEM_PROMPT = """You are the factory assistant for a manufacturing site. Operators, \
maintenance staff and engineers ask you about the site's equipment (pumps, motors, conveyors, \
robots, controllers or anything else in the asset catalog): its current status, its sensor \
telemetry, and the operations recorded against it.

You learn about the plant only through your tools, which read the site's equipment catalog, \
sensor history and operation log. Equipment differs from site to site, so do not assume what \
exists: call list_equipment when you don't know the tag, and get_equipment to see an item's \
assets, sensor channels, units and limits before interpreting its readings.

Answer only from what the tools return. In every answer about equipment, name its tag and the \
time window you looked at. When a value is outside its limit, or a trend is rising or falling, \
say so with the number and unit. If several signals move together, say what pattern that is \
consistent with (for example, rising vibration with falling flow and pressure is consistent \
with cavitation), and present it as a likely cause to check, not a diagnosis. If the tools \
return no data or an error, say that plainly instead of guessing.

If the user asks about you or your tools (what a tool does, what you can see), explain it in \
plain language without calling tools. Keep answers short: a few sentences or a short list."""

MAX_HISTORY = 40


@dataclass
class HistoryMessage:
    role: Literal["user", "assistant"]
    content: str


@dataclass
class Reply:
    text: str
    tools_used: list[dict]
    model: str


def _messages(history: list[HistoryMessage], content: str) -> list[dict]:
    """Alternating user/assistant messages starting with a user turn, ending with `content`."""
    messages: list[dict] = []
    for m in history[-MAX_HISTORY:]:
        if not m.content.strip() or (not messages and m.role != "user"):
            continue
        if messages and messages[-1]["role"] == m.role:
            messages[-1]["content"] += "\n\n" + m.content
        else:
            messages.append({"role": m.role, "content": m.content})
    if messages and messages[-1]["role"] == "user":
        messages[-1]["content"] += "\n\n" + content
    else:
        messages.append({"role": "user", "content": content})
    return messages


def _claude_tools(box: Toolbox) -> list:
    @beta_async_tool
    async def list_equipment() -> str:
        """List all equipment (tag, name, station, current status)."""
        return as_text(await box.run("list_equipment", {}))

    @beta_async_tool
    async def get_equipment(equipment: str) -> str:
        """Get one piece of equipment: status, installed assets, sensor channels with their normal
        limits, and the last factory operation.

        Args:
            equipment: Equipment tag as returned by list_equipment, e.g. PUMP-01.
        """
        return as_text(await box.run("get_equipment", {"equipment": equipment}))

    @beta_async_tool
    async def get_telemetry_summary(equipment: str, window_minutes: int = 15) -> str:
        """Summarize sensor telemetry for the equipment over a recent window: per sensor tag the
        sample count, min, max, average, last value, slope per minute, trend (rising, falling,
        steady) and how many samples were outside the channel's limits.

        Args:
            equipment: Equipment tag as returned by list_equipment, e.g. PUMP-01.
            window_minutes: How far back to look, in minutes (1 to 10080). Default 15.
        """
        args = {"equipment": equipment, "window_minutes": window_minutes}
        return as_text(await box.run("get_telemetry_summary", args))

    @beta_async_tool
    async def get_operations(equipment: str, limit: int = 10) -> str:
        """List the most recent factory operations on the equipment (start, stop, fault, clear,
        setpoint), newest first, with parameters, actor and time.

        Args:
            equipment: Equipment tag as returned by list_equipment, e.g. PUMP-01.
            limit: How many operations to return (1 to 50). Default 10.
        """
        return as_text(await box.run("get_operations", {"equipment": equipment, "limit": limit}))

    return [list_equipment, get_equipment, get_telemetry_summary, get_operations]


async def _run_claude(box: Toolbox, history: list[HistoryMessage], content: str) -> str:
    s = get_settings()
    client = anthropic.AsyncAnthropic(api_key=s.anthropic_api_key)
    runner = client.beta.messages.tool_runner(
        model=s.agent_model,
        max_tokens=16000,
        system=SYSTEM_PROMPT,
        tools=_claude_tools(box),
        messages=_messages(history, content),
        output_config={"effort": s.agent_effort},
        max_iterations=s.agent_max_tool_calls + 2,
        # Re-run a refused request on a fallback model chosen by refusal category.
        betas=["server-side-fallback-2026-07-01"],
        fallbacks="default",
    )
    final = await runner.until_done()
    if final.stop_reason == "refusal":
        return "Sorry, I can't help with that request."
    text = "".join(b.text for b in final.content if b.type == "text").strip()
    return text or "I couldn't put together an answer from the data."


EQUIPMENT_TAG = re.compile(r"\b([A-Za-z]{2,}-\d{1,4})\b")


def _fmt(v: float) -> str:
    return f"{v:.2f}".rstrip("0").rstrip(".")


async def _run_offline(box: Toolbox, history: list[HistoryMessage], content: str) -> str:
    """Rule-based stand-in for Claude: same tools, templated answer. For keyless automation."""
    text = content.lower()
    match = EQUIPMENT_TAG.search(content) or next(
        (EQUIPMENT_TAG.search(m.content) for m in reversed(history) if EQUIPMENT_TAG.search(m.content)),
        None,
    )
    equipment = await box.run("list_equipment", {})
    if isinstance(equipment, dict):
        return f"I couldn't reach core-svc: {equipment.get('error')}."
    if not match and (len(equipment) != 1 or re.search(r"\b(list|which|what) (equipment|machines|assets|pumps|motors)", text)):
        rows = ", ".join(f"{e['tag']} ({e.get('status') or 'unknown'})" for e in equipment)
        return f"Equipment: {rows or 'none found'}."
    tag = match.group(1).upper() if match else equipment[0]["tag"]

    detail = await box.run("get_equipment", {"equipment": tag})
    if "error" in detail:
        return f"I couldn't find {tag}: {detail['error']}."
    window_min = 5
    summary = await box.run("get_telemetry_summary", {"equipment": tag, "window_minutes": window_min})
    ops = await box.run("get_operations", {"equipment": tag, "limit": 3})

    lines = [f"{tag} ({detail['name']}) is {detail.get('status') or 'unknown'}."]
    tags = summary.get("tags", []) if isinstance(summary, dict) else []
    if not tags:
        lines.append(f"No telemetry in the last {window_min} min.")
    for t in tags:
        unit = t.get("unit") or ""
        note = f"{t['tag']}: last {_fmt(t['last'])} {unit}, avg {_fmt(t['avg'])}, {t['trend']}"
        if t.get("slope_per_min") is not None and t["trend"] != "steady":
            note += f" ({_fmt(t['slope_per_min'])} {unit}/min)"
        if t["out_of_limit"]:
            note += f", {t['out_of_limit']} of {t['samples']} samples out of limit"
        if t["last_out_of_limit"]:
            lo, hi = t.get("lo_limit"), t.get("hi_limit")
            band = f"{_fmt(lo)}-{_fmt(hi)}" if lo is not None and hi is not None else "normal"
            note += f", now OUTSIDE its {band} {unit} band"
        lines.append(f"- {note}")
    if tags:
        lines.insert(1, f"Last {window_min} min of telemetry:")
    if isinstance(ops, list) and ops:
        last = ops[0]
        lines.append(f"Last operation: {last['op']} by {last['actor']} at {last['ts']}.")
    return "\n".join(lines)


async def run_turn(history: list[HistoryMessage], content: str, core: CoreSvc | None = None) -> Reply:
    s = get_settings()
    own_core = core is None
    core = core or CoreSvc()
    box = Toolbox(core, max_calls=s.agent_max_tool_calls)
    model = "offline" if s.offline else s.agent_model
    run = _run_offline if s.offline else _run_claude
    try:
        text = await asyncio.wait_for(run(box, history, content), timeout=s.agent_timeout_s)
    except CoreSvcError as err:
        text = f"I couldn't reach core-svc: {err}."
    finally:
        if own_core:
            await core.aclose()
    return Reply(text=text, tools_used=[asdict(c) for c in box.calls], model=model)
