from time import time


def get_ttl_hash(cache_seconds: int = 3600) -> int:
    """Return the same value within `cache_seconds` time period"""
    return round(time() / cache_seconds)
