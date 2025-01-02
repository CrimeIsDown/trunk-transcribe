#!/bin/bash

set -Eeou pipefail

DOCKER_COMPOSE=$(docker compose > /dev/null 2>&1 && echo "docker compose" || echo "docker-compose")

build() {
	$DOCKER_COMPOSE build
}

start() {
	if [ ! -f .env ]; then
		echo "Missing .env file; copy from .env.example and edit"
		exit 1
	fi
	if [ ! -f config/notifications.json ]; then
		echo "Missing config/notifications.json file; copy from config/notifications.json.example and edit"
		exit 1
	fi
	$DOCKER_COMPOSE up -d
}

stop() {
	$DOCKER_COMPOSE stop
}

deps() {
	bin/install-whisper.sh
	uv sync
}

lint() {
	uv run -- mypy app
	uv run -- ruff check app
	uv run -- ruff format app --check
}

fmt() {
	uv run -- ruff check app --fix
	uv run -- ruff format app
	uv run -- ruff check tests --fix
	uv run -- ruff format tests
}

restart() {
	$DOCKER_COMPOSE restart api worker
}

test() {
	start
	uv run python3 tests/wait_for_api.py
	uv run python3 -m pytest $@
}

retest() {
	restart
	test $@
}

if [ -z "$1" ]; then
	echo "Usage: $0 <command>"
	exit 1
fi

$1 "${@:2}"
