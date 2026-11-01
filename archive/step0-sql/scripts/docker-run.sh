#!/usr/bin/env bash
# Start MySQL 9 (if needed) and run one chatbotpy command in the app container.
# Usage: scripts/docker-run.sh [command args...]     (default: ping)
#   scripts/docker-run.sh ping --target mes
#   scripts/docker-run.sh analyze_datasource_schema --target mes --columns
set -euo pipefail
cd "$(dirname "$0")/.."

# The Node app's DB is on the host, so point the container at host.docker.internal.
# The URL is read from .env and never printed.
if [[ -f .env ]]; then
  url="$(grep -E '^CHATBOTJS_DB_URL=' .env | tail -1 | cut -d= -f2- || true)"
  if [[ -n "$url" && "$url" != *CHANGE_ME* ]]; then
    url="${url//@127.0.0.1:/@host.docker.internal:}"
    export CHATBOTJS_DB_URL_DOCKER="${url//@localhost:/@host.docker.internal:}"
  fi
fi

docker compose up -d --wait db >/dev/null
if [[ $# -eq 0 ]]; then set -- ping; fi
exec docker compose run --rm app "$@"
