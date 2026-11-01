"""FastAPI app: POST /agent/turn and GET /health. Called by the Node chatbot server."""

import logging

import anthropic
from fastapi import FastAPI
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field

from app.agent.harness import HistoryMessage, run_turn
from app.config import get_settings
from app.integrations.core_svc import CoreSvc

log = logging.getLogger("chatbotpy")
app = FastAPI(title="chatbotpy", version="0.2.0")


class HistoryItem(BaseModel):
    role: str
    content: str


class TurnRequest(BaseModel):
    session_id: str | None = None
    history: list[HistoryItem] = Field(default_factory=list)
    content: str = Field(min_length=1, max_length=4000)


def error(status: int, message: str) -> JSONResponse:
    return JSONResponse({"error": message}, status_code=status)


@app.post("/agent/turn")
async def agent_turn(req: TurnRequest):
    history = [HistoryMessage(h.role, h.content) for h in req.history if h.role in ("user", "assistant")]
    try:
        reply = await run_turn(history, req.content.strip())
    except TimeoutError:
        return error(504, "The agent took too long to answer.")
    except anthropic.APIStatusError as err:
        log.exception("model call failed session=%s", req.session_id)
        return error(502, f"The model call failed ({err.status_code}).")
    except anthropic.APIConnectionError:
        log.exception("model unreachable session=%s", req.session_id)
        return error(502, "The model could not be reached.")
    return {"reply": reply.text, "tools_used": reply.tools_used, "model": reply.model}


@app.get("/health")
async def health():
    s = get_settings()
    core = CoreSvc()
    try:
        core_health = await core.health()
    finally:
        await core.aclose()
    ok = core_health.get("status") == "ok"
    body = {
        "status": "ok" if ok else "degraded",
        "core_svc": core_health,
        "model": "offline" if s.offline else s.agent_model,
    }
    return JSONResponse(body, status_code=200 if ok else 503)
