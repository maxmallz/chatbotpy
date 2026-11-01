#!/usr/bin/env bash
# Build the chatbotpy image. Usage: scripts/docker-build.sh [--dev]
#   --dev  include pytest and ruff in the image
set -euo pipefail
cd "$(dirname "$0")/.."

INSTALL_DEV=0
[[ "${1:-}" == "--dev" ]] && INSTALL_DEV=1

export INSTALL_DEV
docker compose build app
echo "built chatbotpy:dev (INSTALL_DEV=$INSTALL_DEV)"
