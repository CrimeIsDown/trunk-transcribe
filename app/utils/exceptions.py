import os
from sentry_sdk.types import Event, Hint

from app.whisper.exceptions import WhisperException

class BaseException(Exception): ...


def before_send(event: Event, hint: Hint):
    exc_type, exc_value, tb = hint.get("exc_info", [None, None, None])
    if exc_type == WhisperException:
        return None
    if os.getenv("S3_PUBLIC_URL", "") in str(exc_value) or "Could not access attachment" in str(exc_value):
        return None
    return event
