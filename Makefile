SHELL := /bin/bash

build:
	docker compose build

start:
	docker compose up -d

stop:
	docker compose stop

deps:
	./install-whisper.sh
	poetry install --with dev

fmt:
	black app tests *.py --exclude app/notification_plugins/NotifyTelegram.py

restart: start
	docker compose restart api worker

test:
	@diff config/whisper.json config/whisper.json.testing
	docker compose exec api python3 -m unittest

restart-and-test: restart test

.PHONY: build deps fmt restart test
