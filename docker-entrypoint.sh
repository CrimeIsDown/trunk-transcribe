#!/usr/bin/env bash
set -Eeo pipefail

if [ "$1" = 'web' ]; then
    exec uvicorn app.api:app --host 0.0.0.0
elif [ "$1" = 'worker' ]; then
    if [ -z "$CELERY_HOSTNAME" ]; then
        CELERY_HOSTNAME="celery-${GIT_COMMIT::7}"
        if [ -f /root/.vast_containerlabel ]; then
            CELERY_HOSTNAME="$CELERY_HOSTNAME@$(cat /root/.vast_containerlabel)"
        else
            CELERY_HOSTNAME="$CELERY_HOSTNAME@%n"
        fi
    fi
    exec celery --app=app.worker.celery worker \
        -P ${CELERY_POOL:-prefork} \
        -c ${CELERY_CONCURRENCY:-2} \
        -l ${CELERY_LOGLEVEL:-info} \
        -n $CELERY_HOSTNAME \
        -Q ${CELERY_QUEUES:-transcribe}
elif [ "$1" = 'flower' ]; then
    exec celery --app=app.worker.celery flower --port=5555
fi

exec "$@"
