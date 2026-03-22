#!/usr/bin/env bash
set -Eeuo pipefail

cd "$(dirname "${BASH_SOURCE[0]}")/.."

uv run mypy app
uv run ruff check app tests scripts
uv run ruff format app tests scripts --check
