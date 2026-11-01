---
name: ping
description: Ping chatbotpy's datasources (app and mes on MySQL 9, chatbotjs on the Node app's MySQL 8.4) and report whether each is reachable, its MySQL version, VECTOR support, user, latency and read-only status. Use when asked to ping, check or test the database connection, or before any step that needs the database.
allowed-tools: Bash(.venv/bin/python -m app ping*)
---

# ping

Run from the repo root:

```bash
.venv/bin/python -m app ping                 # all datasources
.venv/bin/python -m app ping --target mes    # one of: app, mes, chatbotjs
.venv/bin/python -m app ping --json          # structured output
```

URLs come from `.env` (`APP_DB_URL`, `MES_DB_URL`, `CHATBOTJS_DB_URL`). Passwords are masked in the output. Exit code 0 means every target answered.

If `.venv` is missing, set it up first: `python3 -m venv .venv && .venv/bin/pip install -e ".[dev]"`.

## Report

One line per target: OK/FAIL, MySQL version, latency. Then flag only what's wrong:

- **FAIL**: give the likely cause from the error. `Can't connect` / `Connection refused` means the container is down or the port is wrong (MySQL 9 is on 3037, Node app's MySQL 8.4 on 3036, see `docker ps`). `Access denied` means wrong user or password in `.env`. `Unknown database` means the schema hasn't been created yet (step 1 `db-up`).
- `mes` or `chatbotjs` reporting `read-write`: the read-only session setting didn't apply. Say so loudly.
- `app` or `mes` without VECTOR support (MySQL < 9): analysis embeddings won't work there.
- `chatbotjs` without VECTOR is expected (MySQL 8.4), so don't flag it.

Never print the contents of `.env` or the passwords in it.
