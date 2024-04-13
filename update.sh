#!/bin/bash
set -ex

git checkout main
git pull

# Check if .env contains the correct values
if ! grep -q "COMPOSE_FILE=docker-compose.yml" .env; then
    echo "The .env file settings have recently changed. Please update the COMPOSE_FILE variable to include docker-compose.server.yml instead of docker-compose.yml, and add docker-compose.worker.yml if you want to run the transcription worker as well. Refer to .env.example for more information."
    exit 1
fi

docker compose pull
docker compose up -d $(docker compose ps --services)

# Optionally, reindex search calls if there was a change to the search schema
# docker logs -f $(docker compose run -d api bin/reindex.py --update-settings)
