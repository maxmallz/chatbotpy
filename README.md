# chatbotpy

The agentic part of the factory stack in [ACUTE-PLAN.md](ACUTE-PLAN.md). It answers questions about factory equipment by calling **nest core-svc over HTTP**. **chatbotpy runs no SQL and holds no database URLs**, and [tests/test_no_sql.py](tests/test_no_sql.py) enforces that.

```text
Node chatbot :3000 ──POST /agent/turn {history, content}──▶ chatbotpy :8088 ──HTTP──▶ core-svc :8080 ──▶ MySQL :3306 / ClickHouse :8123
```

The Node chatbot (`../chatbot`) owns the UI and the chat history (`sessions`, `messages` in its MySQL on :3036). It sends the whole history on every turn, so chatbotpy keeps no state of its own.

## Agent

| Piece | File |
| --- | --- |
| HTTP API: `POST /agent/turn`, `GET /health` | [app/main.py](app/main.py) |
| `run_turn()`: Claude tool runner, or the offline agent | [app/agent/harness.py](app/agent/harness.py) |
| Tools, recording every call and enforcing the per-turn limit | [app/agent/tools.py](app/agent/tools.py) |
| core-svc client | [app/integrations/core_svc.py](app/integrations/core_svc.py) |

**Tools** (all read-only GETs on core-svc):

| Tool | core-svc route |
| --- | --- |
| `list_equipment` | `/equipment` |
| `get_equipment` | `/equipment/{tag}` |
| `get_telemetry_summary` | `/equipment/{tag}/telemetry/summary` |
| `get_operations` | `/equipment/{tag}/operations` |

**Model.** By default the agent is Claude (`claude-opus-5-5`) through the official `anthropic` SDK's tool runner, with effort `low` and server-side refusal fallbacks turned on. Setting `AGENT_MODEL=offline`, or leaving `ANTHROPIC_API_KEY` empty, switches to a rule-based agent instead. It calls the same tools and writes a templated answer, so the stack and its automation run without a key.

## Run

```bash
python3 -m venv .venv && .venv/bin/pip install -e ".[dev]"
cp .env.example .env                    # set ANTHROPIC_API_KEY for Claude
.venv/bin/python -m app serve           # :8088
.venv/bin/python -m app ask "How is PUMP-01 doing?"
.venv/bin/pytest -q && .venv/bin/ruff check app tests
```

To run the whole stack (MySQL, ClickHouse, core-svc, chatbotpy and the Node chatbot) plus the factory and agent scenario, use `../nest/scripts/stack.sh up|status|run|down|debug`.

## API

`POST /agent/turn`

```json
{ "session_id": "b7f2…", "history": [{"role": "user", "content": "…"}, {"role": "assistant", "content": "…"}], "content": "How is PUMP-01 doing?" }
```

returns

```json
{ "reply": "PUMP-01 (Cooling water pump 1) is Faulted. …", "tools_used": [{"name": "get_telemetry_summary", "args": {"equipment": "PUMP-01", "window_minutes": 5}, "ok": true, "error": null}], "model": "claude-opus-5-5" }
```

Errors are `{"error": "..."}`: 422 for a bad body, 502 when the model call fails, 504 when the agent runs past 60 s.
