from celery import Task as CeleryTask


class Task(CeleryTask):
    autoretry_for = (Exception,)
    max_retries = 5
    retry_backoff = True
    retry_backoff_max = 600
    retry_jitter = True
