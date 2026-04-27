#!/usr/bin/env bash
set -Eeuo pipefail

shutdown_container() {
    echo "Celery worker healthcheck failed; stopping container for restart" >&2
    kill -s 15 1
    sleep "${CELERY_HEALTHCHECK_SHUTDOWN_GRACE_SECONDS:-10}"
    kill -s 9 1
}

expand_celery_hostname() {
    local value="$1"
    local full_hostname
    local short_hostname
    local domain

    full_hostname="$(hostname -f 2>/dev/null || hostname)"
    short_hostname="$(hostname -s 2>/dev/null || hostname)"
    domain="${full_hostname#"$short_hostname"}"
    domain="${domain#.}"

    value="${value//%h/$full_hostname}"
    value="${value//%n/$short_hostname}"
    value="${value//%d/$domain}"

    printf '%s' "$value"
}

celery_hostname="${CELERY_HOSTNAME-}"
if [ -z "$celery_hostname" ]; then
    celery_hostname="celery"
    if [ -n "${GIT_COMMIT-}" ]; then
        celery_hostname="${celery_hostname}-${GIT_COMMIT::7}"
    fi
    if [ -f /root/.vast_containerlabel ]; then
        celery_hostname="$celery_hostname@$(cat /root/.vast_containerlabel)"
    else
        celery_hostname="$celery_hostname@%n"
    fi
fi

celery_destination="$(expand_celery_hostname "$celery_hostname")"
timeout_seconds="${CELERY_HEALTHCHECK_TIMEOUT_SECONDS:-10}"

if uv run --directory backend celery --app=app.worker.celery inspect \
    --timeout "$timeout_seconds" \
    --destination "$celery_destination" \
    ping >/tmp/celery-healthcheck.out 2>/tmp/celery-healthcheck.err; then
    exit 0
fi

cat /tmp/celery-healthcheck.out >&2 || true
cat /tmp/celery-healthcheck.err >&2 || true
shutdown_container
