import json
import os
from functools import lru_cache


@lru_cache()
def get_transcript_cleanup_config(ttl_hash=None) -> list[dict]:  # type: ignore
    del ttl_hash

    config = "config/transcript_cleanup.json"
    if os.path.isfile(config):
        with open(config) as file:
            return json.load(file)  # type: ignore
    return []
