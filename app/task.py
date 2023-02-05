import logging
from celery import Task as CeleryTask, states, exceptions


class Task(CeleryTask):
    autoretry_for = (Exception,)
    max_retries = 5
    retry_backoff = True
    retry_backoff_max = 600
    retry_jitter = True

    task_counts = {
        states.SUCCESS: 0,
        states.FAILURE: 0,
        states.RETRY: 0,
    }

    def before_start(self, task_id, args, kwargs):
        super().before_start(task_id, args, kwargs)

        # If we've only had failing tasks on this worker, terminate it
        if self.task_counts[states.SUCCESS] == 0 and (
            self.task_counts[states.FAILURE] > 5 or self.task_counts[states.RETRY] > 10
        ):
            logging.fatal(
                "Exceeded job failure threshold, exiting...\n" + str(self.task_counts)
            )
            raise exceptions.WorkerTerminate(1)

    def on_success(self, retval, task_id, args, kwargs):
        super().on_success(retval, task_id, args, kwargs)
        self.task_counts[states.SUCCESS] += 1

    def on_retry(self, exc, task_id, args, kwargs, einfo):
        super().on_retry(exc, task_id, args, kwargs, einfo)
        self.task_counts[states.RETRY] += 1

    def on_failure(self, exc, task_id, args, kwargs, einfo):
        super().on_failure(exc, task_id, args, kwargs, einfo)
        self.task_counts[states.FAILURE] += 1
