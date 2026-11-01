"""chatbotpy command line: `python -m app <command>`."""

import argparse
import asyncio
import json

import httpx

from app.agent.harness import run_turn
from app.config import get_settings


def cmd_serve(args: argparse.Namespace) -> int:
    import uvicorn

    s = get_settings()
    uvicorn.run("app.main:app", host=args.host or s.host, port=args.port or s.port,
                reload=args.reload, log_level="info")
    return 0


def cmd_ask(args: argparse.Namespace) -> int:
    reply = asyncio.run(run_turn([], args.text))
    if args.json:
        print(json.dumps({"reply": reply.text, "tools_used": reply.tools_used, "model": reply.model},
                         indent=2))
    else:
        print(reply.text)
        tools = ", ".join(f"{c['name']}{'' if c['ok'] else ' (failed)'}" for c in reply.tools_used)
        print(f"\n[{reply.model}] tools: {tools or 'none'}")
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="python -m app")
    sub = parser.add_subparsers(dest="command", required=True)

    p = sub.add_parser("serve", help="run the HTTP API (POST /agent/turn)")
    p.add_argument("--host")
    p.add_argument("--port", type=int)
    p.add_argument("--reload", action="store_true")
    p.set_defaults(func=cmd_serve)

    p = sub.add_parser("ask", help="run one agent turn and print the reply")
    p.add_argument("text")
    p.add_argument("--json", action="store_true")
    p.set_defaults(func=cmd_ask)

    args = parser.parse_args(argv)
    try:
        return args.func(args)
    except httpx.HTTPError as err:
        print(f"error: {err}")
        return 1
