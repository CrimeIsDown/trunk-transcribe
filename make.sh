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
	uv sync --directory backend
}

lint() {
	uv run --directory backend -- mypy app
	uv run --directory backend -- ruff check app
	uv run --directory backend -- ruff format app --check
}

fmt() {
	uv run --directory backend -- ruff check app --fix
	uv run --directory backend -- ruff format app
	uv run --directory backend -- ruff check tests --fix
	uv run --directory backend -- ruff format tests
}

restart() {
	$DOCKER_COMPOSE restart api worker
}

test() {
	start
	uv run --directory backend python3 tests/wait_for_api.py
	uv run --directory backend python3 -m pytest $@
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
