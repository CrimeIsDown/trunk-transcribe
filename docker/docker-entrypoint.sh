#!/usr/bin/env bash
set -Eeou pipefail

if [ "$1" = 'api' ]; then
    # Clean up any old temp files
    /bin/sh -c "while true; do find /tmp -type f -mmin +10 -delete; sleep 60; done" &
    disown

    exec poetry run uvicorn app.api:app --host 0.0.0.0 --log-level ${UVICORN_LOG_LEVEL:-info}
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

    exec poetry run celery --app=app.worker.celery worker \
        -P ${CELERY_POOL:-prefork} \
        -c ${CELERY_CONCURRENCY:-1} \
        -l ${CELERY_LOGLEVEL:-info} \
        -n $CELERY_HOSTNAME \
        -Q ${CELERY_QUEUES:-transcribe}
elif [ "$1" = 'flower' ]; then
    exec poetry run celery --app=app.worker.celery flower --port=5555
fi

exec "$@"
