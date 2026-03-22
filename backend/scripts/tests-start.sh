#!/usr/bin/env bash
set -Eeuo pipefail

cd "$(dirname "${BASH_SOURCE[0]}")/.."

python tests/wait_for_api.py
python -m pytest "$@"
