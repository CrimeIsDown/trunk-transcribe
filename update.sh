#!/bin/bash
set -ex

git checkout main
git pull

echo "The .env file settings have recently changed. Please ensure your COMPOSE_FILE variable has all the proper services enabled that you want. Refer to .env.example for more information."

if [ -f .env ]; then
  set -a
  # shellcheck source=/dev/null
  source .env
  set +a
fi

docker compose pull

PROJECT_NAME="${COMPOSE_PROJECT_NAME:-$(basename "$PWD")}"
POSTGRES_VOLUME="${PROJECT_NAME}_postgres-data"
POSTGRES_IMAGE_TAG="${POSTGRES_VERSION:-latest}"

if docker volume inspect "${POSTGRES_VOLUME}" >/dev/null 2>&1; then
  UPGRADE_INFO="$(docker run --rm -v "${POSTGRES_VOLUME}:/var/lib/postgresql" "postgres:${POSTGRES_IMAGE_TAG}" bash -lc '
set -euo pipefail
pg_major="$(postgres --version | awk "{print \$3}" | cut -d. -f1)"
old_dir="/var/lib/postgresql/data"
new_dir="/var/lib/postgresql/${pg_major}/data"
if [ -f "${old_dir}/PG_VERSION" ] && [ ! -f "${new_dir}/PG_VERSION" ]; then
  old_major="$(tr -d "[:space:]" < "${old_dir}/PG_VERSION" | cut -d. -f1)"
  echo "NEEDS_UPGRADE ${old_major} ${pg_major}"
fi
')" || true

  if echo "${UPGRADE_INFO}" | grep -q '^NEEDS_UPGRADE '; then
    OLD_MAJOR="$(echo "${UPGRADE_INFO}" | awk '{print $2}')"
    NEW_MAJOR="$(echo "${UPGRADE_INFO}" | awk '{print $3}')"
    echo "Upgrading Postgres data directory from ${OLD_MAJOR} to ${NEW_MAJOR}..."

    docker run --rm \
      -v "${POSTGRES_VOLUME}:/var/lib/postgresql" \
      -e POSTGRES_USER="${POSTGRES_USER:-postgres}" \
      -e POSTGRES_PASSWORD="${POSTGRES_PASSWORD:-}" \
      -e POSTGRES_INITDB_ARGS="${POSTGRES_INITDB_ARGS:-}" \
      "postgres:${POSTGRES_IMAGE_TAG}" \
      bash -lc '
set -euo pipefail
pg_major="$(postgres --version | awk "{print \$3}" | cut -d. -f1)"
old_dir="/var/lib/postgresql/data"
new_dir="/var/lib/postgresql/${pg_major}/data"
old_major="$(tr -d "[:space:]" < "${old_dir}/PG_VERSION" | cut -d. -f1)"

if [ ! -x "/usr/lib/postgresql/${old_major}/bin/postgres" ]; then
  apt-get update
  apt-get install -y --no-install-recommends "postgresql-${old_major}"
  rm -rf /var/lib/apt/lists/*
fi

mkdir -p "${new_dir}"
chown -R postgres:postgres /var/lib/postgresql

pwfile=""
if [ -n "${POSTGRES_PASSWORD-}" ]; then
  pwfile="$(mktemp)"
  printf "%s" "${POSTGRES_PASSWORD}" > "${pwfile}"
  chown postgres:postgres "${pwfile}"
  chmod 600 "${pwfile}"
fi

initdb_args=()
if [ -n "${POSTGRES_USER-}" ]; then
  initdb_args+=("--username=${POSTGRES_USER}")
fi
if [ -n "${pwfile}" ]; then
  initdb_args+=("--pwfile=${pwfile}")
fi
if [ -n "${POSTGRES_INITDB_ARGS-}" ]; then
  initdb_args+=(${POSTGRES_INITDB_ARGS})
fi

su - postgres -c "/usr/lib/postgresql/${pg_major}/bin/initdb -D ${new_dir} ${initdb_args[*]}"
su - postgres -c "/usr/lib/postgresql/${pg_major}/bin/pg_upgrade \
  --old-bindir=/usr/lib/postgresql/${old_major}/bin \
  --new-bindir=/usr/lib/postgresql/${pg_major}/bin \
  --old-datadir=${old_dir} \
  --new-datadir=${new_dir} \
  --link"

if [ -n "${pwfile}" ]; then
  rm -f "${pwfile}"
fi
'
  fi
fi

read -p "Would you like to run database migrations? (y/n) " -n 1 -r
echo
if [[ $REPLY =~ ^[Yy]$ ]]; then
  docker compose run --rm api uv run alembic upgrade head
fi

docker compose up -d $(docker compose ps --services)

# Optionally, reindex search calls if there was a change to the search schema
# docker logs -f $(docker compose run -d api bin/reindex.py --update-settings)
