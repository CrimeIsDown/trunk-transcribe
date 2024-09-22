import os
from sentry_sdk.types import Event, Hint


class BaseException(Exception): ...


def before_send(event: Event, hint: Hint):
    exc_type, exc_value, tb = hint.get("exc_info", [None, None, None])
    # We need to do the comparison like this to avoid a circular import error
    if "WhisperException" in str(exc_type):
        return None
    if os.getenv("S3_PUBLIC_URL", "") in str(
        exc_value
    ) or "Could not access attachment" in str(exc_value):
        return None
    return event
