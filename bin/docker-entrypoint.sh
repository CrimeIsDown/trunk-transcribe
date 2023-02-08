#!/usr/bin/env bash
set -Eeou pipefail

if [ "$1" = 'api' ]; then
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
    # Make sure we can connect to these hosts
    if [ -f .env ]; then
        export $(grep -E '^(MEILI_URL|API_BASE_URL|S3_ENDPOINT)' .env | xargs)
    fi
    curl -sS "$MEILI_URL" > /dev/null
    curl -sS "$API_BASE_URL" > /dev/null
    curl -sS "$S3_ENDPOINT" > /dev/null

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
