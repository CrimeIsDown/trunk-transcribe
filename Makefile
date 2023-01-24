build:
	docker compose build

start:
	docker compose up -d

deps:
	pip install -r requirements.txt -r requirements-dev.txt

fmt:
	black app tests *.py --exclude app/notification_plugins/NotifyTelegram.py

restart: start
	docker compose restart api worker

test:
	python -m unittest

restart-and-test: restart test

.PHONY: build deps fmt restart test
