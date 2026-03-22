from celery import Task as CeleryTask

from app.whisper.exceptions import WhisperException


class Task(CeleryTask):
    autoretry_for = (Exception,)
    dont_autoretry_for = (WhisperException,)
    max_retries = 5
    retry_backoff = True
    retry_backoff_max = 600
    retry_jitter = True
