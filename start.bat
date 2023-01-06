call .\.venv\Scripts\activate
set TELEGRAM_BOT_TOKEN=
set CELERY_BROKER_URL=
set CELERY_RESULT_BACKEND=
set API_BASE_URL=
set WHISPER_MODEL=medium.en
set TYPESENSE_API_KEY=
set TYPESENSE_HOST=
for /f %%i in ('git rev-parse --short HEAD') do set GIT_COMMIT=%%i
celery --app=app.worker.celery worker --loglevel=info -c 1 -P gevent -n celery-%GIT_COMMIT%@%%n
