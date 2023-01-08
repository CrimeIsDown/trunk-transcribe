#!/usr/bin/env bash
set -Eeo pipefail

if [ "$1" = 'web' ]; then
    exec uvicorn app.api:app --host 0.0.0.0
elif [ "$1" = 'worker' ]; then
    exec celery --app=app.worker.celery worker \
        -P gevent \
        -c 1 \
        -l ${CELERY_LOGLEVEL:-info} \
        -n celery-${GIT_COMMIT::7}@%n
elif [ "$1" = 'flower' ]; then
    exec celery --app=app.worker.celery flower --port=5555
fi

exec "$@"
