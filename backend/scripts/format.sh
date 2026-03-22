#!/usr/bin/env bash
set -Eeuo pipefail

cd "$(dirname "${BASH_SOURCE[0]}")/.."

uv run ruff check app tests scripts --fix
uv run ruff format app tests scripts
