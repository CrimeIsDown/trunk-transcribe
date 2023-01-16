import re


def format_task(task):
    if task.name == "transcribe":
        task.kwargs = re.sub(
            r"'audio_file_b64': '(.*)'", "'audio_file_b64': '...'", task.kwargs
        )
    return task
