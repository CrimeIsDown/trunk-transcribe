#!/bin/bash
set -ex

git checkout main
git pull
docker compose pull
docker compose up -d $(docker compose ps --services)

# Optionally, reindex search calls if there was a change to the search schema
# docker logs -f $(docker compose run -d api bin/reindex.py --update-settings)
