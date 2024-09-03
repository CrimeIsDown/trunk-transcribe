#!/bin/bash
set -ex

git checkout main
git pull

echo "The .env file settings have recently changed. Please ensure your COMPOSE_FILE variable has all the proper services enabled that you want. Refer to .env.example for more information."

docker compose pull
docker compose up -d $(docker compose ps --services)

# Optionally, reindex search calls if there was a change to the search schema
# docker logs -f $(docker compose run -d api bin/reindex.py --update-settings)
