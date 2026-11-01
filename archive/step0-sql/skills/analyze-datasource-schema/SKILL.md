---
name: analyze-datasource-schema
description: Read the schema and table names (with row estimates, primary keys, indexes, foreign keys and column types) from one of chatbotpy's datasources (app, mes, chatbotjs) and give a short analysis of it. Use when asked to analyze, describe, inspect or summarize a database's schema or tables, or to check a database against what PLAN-chatbotpy.md expects.
allowed-tools: Bash(.venv/bin/python -m app analyze_datasource_schema*), Read
---

# analyze_datasource_schema

Run from the repo root. It only reads `information_schema`, so it is safe on the read-only connections.

```bash
.venv/bin/python -m app analyze_datasource_schema --target mes          # schema from MES_DB_URL
.venv/bin/python -m app analyze_datasource_schema --target chatbotjs    # Node app's DB (MySQL 8.4)
.venv/bin/python -m app analyze_datasource_schema --target app --schema chatbotpy --schema mes
.venv/bin/python -m app analyze_datasource_schema --target app --all-schemas
.venv/bin/python -m app analyze_datasource_schema --target mes --columns   # include column lists
.venv/bin/python -m app analyze_datasource_schema --target mes --json      # full structure
```

The target defaults to `mes`. If the user names a database, map it: "MES" → `mes`, "chatbotpy" or "app" → `app`, "Node", "JS" or "chatbot" → `chatbotjs`. If the command fails to connect, run the `ping` skill to diagnose.

Start with the default text output. Re-run with `--columns` only when the question is about columns or the findings need them.

## Report

Keep it short: at most about 10 bullets, no table dumps.

1. One line per schema: table and view count, rows, size.
2. How it compares with the plan, from the "vs plan" finding. Which of the expected `mes` / `chatbotpy` tables are missing.
3. The shape of the data: core entities, the big time-series tables, and how tables join (declared FKs, or implicit `*_id` keys).
4. Risks for chatbotpy: tables without a primary key, time-series tables whose time column isn't indexed (slow window queries for the domain tools), and VECTOR/JSON columns.
5. For `chatbotjs`, say what overlaps with chatbotpy (for example its `sessions` table) and could be reused or migrated. Never propose writing to it.

Row counts are InnoDB estimates. Say "~" and don't treat 0 as exactly empty.
