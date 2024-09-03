import os


class BaseException(Exception): ...


def before_send(event, hint):  # type: ignore
    if "exc_info" in hint:
        exc_type, exc_value, tb = hint["exc_info"]
        if os.getenv("S3_PUBLIC_URL", "") in str(exc_value):
            return None
    return event
