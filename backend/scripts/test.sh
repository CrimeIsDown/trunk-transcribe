#!/usr/bin/env bash
set -Eeuo pipefail

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"

(
  cd "$REPO_ROOT"
  docker compose up -d
)

cd "$REPO_ROOT/backend"
bash scripts/tests-start.sh "$@"
