#!/usr/bin/env bash
# End-to-end check in Docker: build, start MySQL 9, run unit tests, ping, analyze schemas,
# and confirm the MES connection can't write.
# Usage: scripts/docker-test.sh [--down]    (--down removes the containers and volume afterwards)
set -euo pipefail
cd "$(dirname "$0")/.."

run() { scripts/docker-run.sh "$@"; }
step() { printf '\n==> %s\n' "$*"; }

step "build image (with dev tools)"
scripts/docker-build.sh --dev

step "tests (unit + live against MySQL 9)"
docker compose up -d --wait db >/dev/null
docker compose run --rm --entrypoint pytest app -q

step "ping app + mes (MySQL 9)"
run ping --target app
run ping --target mes

if grep -qE '^CHATBOTJS_DB_URL=.+' .env 2>/dev/null && ! grep -q 'CHANGE_ME' .env; then
  step "ping chatbotjs (Node app MySQL 8.4)"
  run ping --target chatbotjs
else
  step "skip chatbotjs: set CHATBOTJS_DB_URL in .env to include it"
fi

step "analyze mes"
run analyze_datasource_schema --target mes

step "analyze chatbotpy"
run analyze_datasource_schema --target app

step "MES writes are rejected"
if docker compose exec -T db mysql -umes_reader -preaderpass mes \
     -e "INSERT INTO alarms (equipment_id, code, text, severity, start_ts) VALUES ('X','X','x',1,NOW())" \
     2>/dev/null; then
  echo "FAIL: mes_reader was able to write"; exit 1
else
  echo "OK   mes_reader INSERT denied"
fi

if [[ "${1:-}" == "--down" ]]; then
  step "tear down"
  docker compose down -v
fi
printf '\nall checks passed\n'
