call .\.venv\Scripts\activate
for /f %%i in ('git rev-parse --short HEAD') do set GIT_COMMIT=%%i
celery --app=app.worker.celery worker --loglevel=info -c 1 -P gevent -n celery-%GIT_COMMIT%@%%n -Q transcribe
