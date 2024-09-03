#!/usr/bin/env python3

import logging
import os
import sys
from time import sleep

from dotenv import load_dotenv
import requests

load_dotenv()
load_dotenv(".env.testing.local", override=True)

logging.basicConfig(level=logging.INFO)
logging.info("API_BASE_URL: %s", os.getenv("API_BASE_URL"))
logging.info("S3_PUBLIC_URL: %s", os.getenv("S3_PUBLIC_URL"))

tries = 0

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
        if tries > 60:
            sys.exit(1)
        logging.info("Waiting for API to come online...")
        sleep(1)
        tries += 1
