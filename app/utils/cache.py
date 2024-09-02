from time import time


def get_ttl_hash(cache_seconds=3600):  # pragma: no cover
    """Return the same value within `cache_seconds` time period"""
    return round(time() / cache_seconds)
