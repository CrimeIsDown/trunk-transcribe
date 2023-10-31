import logging
import os

import requests


def call(method: str, path: str, json: dict | None = None, params: dict | None = None):
    api_key = os.getenv("API_KEY")
    if api_key:
        headers = {"Authorization": f"Bearer {api_key}"}
    else:
        headers = None

    r = requests.request(
        method=method,
        url=f"{os.getenv('API_BASE_URL')}/{path}",
        timeout=5,
        headers=headers,
        json=json,
        params=params,
    )
    if r.status_code >= 400:
        try:
            logging.error(r.json())
        finally:
            r.raise_for_status()
    return r.json()
