"""chatbotpy command line: `python -m app <command>`."""

import argparse
import json
import sys
from dataclasses import asdict

from sqlalchemy.engine import make_url
from sqlalchemy.exc import DBAPIError

from app.datasource.ping import ping
from app.datasource.schema import analyze, fetch_tables, list_schemas
from app.db import datasources, get_engine


def cmd_ping(args: argparse.Namespace) -> int:
    targets = list(datasources()) if args.target == "all" else [args.target]
    results = [ping(t) for t in targets]
    if args.json:
        print(json.dumps([asdict(r) for r in results], indent=2))
    else:
        for r in results:
            if not r.ok:
                print(f"FAIL {r.target:<9} {r.url}\n     {r.error}")
                continue
            ro = "read-only" if r.read_only else "read-write"
            vec = "vector" if r.supports_vector else "no-vector"
            warn = "  <-- expected read-only" if r.expected_read_only and not r.read_only else ""
            print(f"OK   {r.target:<9} {r.latency_ms} ms  MySQL {r.server_version} ({vec})  "
                  f"{r.current_user}  db={r.database}  {ro}{warn}")
    return 0 if all(r.ok for r in results) else 1


def cmd_analyze_schema(args: argparse.Namespace) -> int:
    ds = datasources()[args.target]
    engine = get_engine(args.target)
    schemas = args.schema or ([make_url(ds.url).database] if not args.all_schemas else [])
    schemas = [s for s in schemas if s] or list_schemas(engine)
    tables = fetch_tables(engine, schemas)
    findings = analyze(tables, schemas)

    if args.json:
        print(json.dumps({"target": args.target, "schemas": schemas,
                          "tables": [asdict(t) for t in tables], "findings": findings},
                         indent=2, default=str))
        return 0

    print(f"# {args.target}: {', '.join(schemas)}\n")
    for schema in schemas:
        print(f"## {schema}")
        for t in (t for t in tables if t.schema == schema):
            kind = " (view)" if t.type != "BASE TABLE" else ""
            pk = f" pk({', '.join(t.primary_key)})" if t.primary_key else ""
            print(f"- {t.name}{kind}: ~{t.rows:,} rows, {len(t.columns)} cols{pk}")
            if args.columns:
                print("    " + ", ".join(f"{c.name}:{c.data_type}" for c in t.columns))
        print()
    print("## Findings")
    for f in findings:
        print(f"- {f}")
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="python -m app")
    sub = parser.add_subparsers(dest="command", required=True)
    names = list(datasources())

    p = sub.add_parser("ping", help="connect to datasources and report status")
    p.add_argument("--target", choices=[*names, "all"], default="all")
    p.add_argument("--json", action="store_true")
    p.set_defaults(func=cmd_ping)

    p = sub.add_parser("analyze_datasource_schema", aliases=["analyze-datasource-schema"],
                       help="list schemas and tables and summarize them")
    p.add_argument("--target", choices=names, default="mes")
    p.add_argument("--schema", action="append",
                   help="schema to analyze (repeatable); default: the URL's database")
    p.add_argument("--all-schemas", action="store_true", help="every non-system schema visible")
    p.add_argument("--columns", action="store_true", help="also print each table's columns")
    p.add_argument("--json", action="store_true")
    p.set_defaults(func=cmd_analyze_schema)

    args = parser.parse_args(argv)
    try:
        return args.func(args)
    except (KeyError, ValueError) as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 2
    except DBAPIError as exc:
        print(f"error: cannot query {getattr(args, 'target', '?')}: {exc.orig} "
              "(run `python -m app ping` to diagnose)", file=sys.stderr)
        return 1
