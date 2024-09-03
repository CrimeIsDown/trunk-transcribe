#!/usr/bin/env python3

import logging
import os
from time import sleep

from dotenv import load_dotenv
import requests

load_dotenv()
load_dotenv(".env.testing.local", override=True)

while True:
    try:
        requests.get(
            url=f"{os.getenv('API_BASE_URL')}/config/notifications.json",
            headers={"Authorization": f"Bearer {os.getenv('API_KEY')}"},
            timeout=5,
        ).raise_for_status()
        requests.get(
            url=f"{os.getenv('S3_PUBLIC_URL')}/init-complete", timeout=5
        ).raise_for_status()
        logging.info("Connected to API successfully.")
        break
    except Exception as e:
        logging.error(e)
        logging.info("Waiting for API to come online...")
        sleep(1)
