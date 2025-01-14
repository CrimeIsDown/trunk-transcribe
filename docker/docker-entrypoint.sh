#!/usr/bin/env bash
set -Eeou pipefail

if [ "$1" = 'api' ]; then
    # Clean up any old temp files
    /bin/sh -c "while true; do find /tmp -type f -mmin +10 -delete; sleep 60; done" &
    disown

    if [ -n "$POSTGRES_HOST" ]; then
        # Check if we have run any DB migrations yet
        CURRENT_DB_VERSION="$(uv run alembic current)"
        if [ -z "$CURRENT_DB_VERSION" ]; then
            uv run alembic upgrade head
        fi
    fi

    exec uv run uvicorn app.api.main:app --host 0.0.0.0 --log-level ${UVICORN_LOG_LEVEL:-info}
elif [ "$1" = 'worker' ]; then
    # Clean up any old temp files
    /bin/sh -c "while true; do find /tmp -type f -mmin +10 -delete; sleep 60; done" &
    disown

    if [ -z "${CELERY_HOSTNAME-}" ]; then
        CELERY_HOSTNAME="celery"
        if [ -n "${GIT_COMMIT-}" ]; then
            CELERY_HOSTNAME="$CELERY_HOSTNAME-${GIT_COMMIT::7}"
        fi
        if [ -f /root/.vast_containerlabel ]; then
            CELERY_HOSTNAME="$CELERY_HOSTNAME@$(cat /root/.vast_containerlabel)"
        else
            CELERY_HOSTNAME="$CELERY_HOSTNAME@%n"
        fi
    fi

    exec uv run celery --app=app.worker.celery worker \
        -P ${CELERY_POOL:-prefork} \
        -c ${CELERY_CONCURRENCY:-1} \
        -l ${CELERY_LOGLEVEL:-info} \
        -n $CELERY_HOSTNAME \
        -Q ${CELERY_QUEUES:-transcribe,post_transcribe}
elif [ "$1" = 'flower' ]; then
    exec uv run celery --app=app.worker.celery flower --port=5555
fi

exec "$@"
