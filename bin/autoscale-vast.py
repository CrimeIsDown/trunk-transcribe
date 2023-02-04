#!/usr/bin/env python3

import argparse
import json
import logging
import os
import subprocess
import time
from functools import lru_cache
from math import floor
from urllib.parse import urlparse

import requests
from dotenv import dotenv_values
from requests.auth import HTTPBasicAuth

prev_delta = 0
interval = 60
last_sleep_duration = 0
last_publish_count = 0
last_deliver_count = 0
vast_api_key = None


def get_queue_status(envs: dict) -> dict:
    parsedurl = urlparse(envs["CELERY_BROKER_URL"])
    rabbitmq_baseurl = parsedurl.netloc[parsedurl.netloc.index("@") + 1 :].replace(
        ":5672", ":15672"
    )
    queue = envs["CELERY_QUEUES"].split(",")[0]
    url = f"http://{rabbitmq_baseurl}/api/queues/%2F/{queue}"
    auth = HTTPBasicAuth(parsedurl.username, parsedurl.password)

    r = requests.get(url, auth=auth, timeout=5)
    r.raise_for_status()
    return r.json()


@lru_cache()
def get_git_commit() -> str:
    if os.getenv("GIT_COMMIT"):
        return os.environ["GIT_COMMIT"][:7]
    p = subprocess.run(
        [
            "git",
            "rev-parse",
            "--short",
            "HEAD",
        ],
        capture_output=True,
    )
    p.check_returncode()
    return p.stdout.decode("utf-8").strip()


def find_available_instances() -> list[dict]:
    # TODO: exclude instances we are already running
    query = {
        "rentable": {"eq": "true"},
        "rented": {"eq": "false"},
        "reliability": {"gt": "0.98"},
        "reliability2": {"gt": "0.98"},
        "num_gpus": {"eq": "1"},
        "gpu_ram": {"gt": "8000.0"},
        "dlperf": {"gt": "8"},
        "dlperf_usd": {"gt": "200"},
        "dlperf_per_dphtotal": {"gt": "200"},
        "dph": {"lte": "0.1"},
        "dph_total": {"lte": "0.1"},
        "cuda_vers": {"gte": "11.7"},
        "cuda_max_good": {"gte": "11.7"},
        "inet_up": {"gte": "90"},
        "inet_down": {"gte": "90"},
        "order": [["dph_total", "asc"]],
        "type": "bid",
    }

    r = requests.get(
        "https://console.vast.ai/api/v0/bundles",
        params={"q": json.dumps(query), "api_key": vast_api_key},
    )
    r.raise_for_status()
    # TODO: Filter this list to exclude any instances we're already renting
    return r.json()["offers"]


def get_current_instances() -> list[dict]:
    r = requests.get(
        "https://console.vast.ai/api/v0/instances",
        params={"owner": "me", "api_key": vast_api_key},
    )
    r.raise_for_status()
    return r.json()["instances"]


def create_instances(count: int, envs: dict, image: str | None = None):
    model = envs["WHISPER_MODEL"] if "WHISPER_MODEL" in envs else "medium.en"
    vram_requirements = {
        "tiny.en": 1.5 * 1024,
        "base.en": 2 * 1024,
        "small.en": 3.5 * 1024,
        "medium.en": 6.5 * 1024,
        "large": 12 * 1024,
    }
    if not image:
        image = f"crimeisdown/trunk-transcribe:main-{model}-cu117"
    instances = find_available_instances()

    while count and len(instances):
        instance = instances.pop(0)
        count -= 1

        instance_id = instance["id"]
        # Bid 1.5x the minimum bid
        bid = round(float(instance["dph_total"]) * 1.5, 6)

        # Adjust concurrency based on GPU RAM
        envs["CELERY_CONCURRENCY"] = str(
            floor(instance["gpu_ram"] / vram_requirements[model])
        )

        # Set a nice hostname so we don't use a random Docker hash
        git_commit = get_git_commit()
        envs["CELERY_HOSTNAME"] = f"celery-{git_commit}@vast-{instance_id}"

        body = {
            "client_id": "me",
            "image": image,
            "args": ["worker"],
            "env": envs,
            "price": bid,
            "disk": 0.5,
            "runtype": "args",
        }

        r = requests.put(
            f"https://console.vast.ai/api/v0/asks/{instance_id}/",
            params={"api_key": vast_api_key},
            json=body,
        )
        r.raise_for_status()
        logging.info(
            f"Started instance {instance_id}, a {instance['gpu_name']} for ${bid}/hr"
        )


def delete_instances(count: int):
    deletable_instances = []

    for instance in get_current_instances():
        if instance["actual_status"] == "exited":
            deletable_instances.append(instance)
        elif count:
            deletable_instances.append(instance)
            count -= 1

    if len(deletable_instances):
        for instance in deletable_instances:
            r = requests.delete(
                f"https://console.vast.ai/api/v0/instances/{instance['id']}/",
                params={"api_key": vast_api_key},
                json={},
            )
            r.raise_for_status()
            logging.info(
                f"Deleted instance {instance['id']}, had status: {instance['status_msg']}"
            )


def autoscale(
    min_instances: int, max_instances: int, throughput: int, image: str | None = None
) -> int:
    envs = dotenv_values(".env.vast")

    queue_status = get_queue_status(envs)
    current_instances = int(queue_status["consumers"])
    message_count = int(queue_status["messages"])
    if current_instances:
        desired_instances = current_instances

        # Figure out how many messages were published and delivered since we last checked
        current_publish_count = int(queue_status["message_stats"]["publish"])
        global last_publish_count
        # Account for counts getting reset
        published_count = (
            current_publish_count - last_publish_count
            if current_publish_count > last_publish_count
            else current_publish_count
        )
        current_deliver_count = int(queue_status["message_stats"]["deliver_get"])
        global last_deliver_count
        # Account for counts getting reset
        delivered_count = (
            current_deliver_count - last_deliver_count
            if current_deliver_count > last_deliver_count
            else current_deliver_count
        )

        # Update our last_ numbers now that we've done our calculation
        last_publish_count = current_publish_count
        last_deliver_count = current_deliver_count

        # If this is our first run, just save the counts for the next time around
        if not last_sleep_duration:
            return 0

        incoming_rate = published_count / last_sleep_duration
        outgoing_rate = delivered_count / last_sleep_duration

        current_throughput = (
            round((outgoing_rate / current_instances) * interval, 1)
            if current_instances
            else 0
        )
        logging.info(
            f"Current throughput: {current_throughput} messages/min per avg instance"
        )

        # If messages are coming in faster than we process them, then scale up
        if incoming_rate > outgoing_rate:
            desired_instances = max(round(message_count / throughput), current_instances)
        # If we're processing messages as fast as we get them, but we have
        # capacity for a higher rate of messages than we're getting, then scale down
        elif (
            incoming_rate <= outgoing_rate
            and throughput * current_instances > delivered_count
        ):
            desired_instances = round(delivered_count / throughput)
    else:
        desired_instances = max(round(message_count / throughput), current_instances)

    scale = (
        min(max_instances, max(min_instances, desired_instances)) - current_instances
    )
    count = abs(scale)
    # Clean up any exited instances
    delete_instances(0)
    if count:
        if scale > 0:
            logging.info(f"Scaling up by {count} instances")
            create_instances(count, envs, image)
        else:
            logging.info(f"Scaling down by {count} instances")
            delete_instances(count)

    return scale


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)

    parser = argparse.ArgumentParser(description="Start workers with vast.ai")
    parser.add_argument(
        "--min-instances",
        type=int,
        metavar="N",
        default=1,
        help="Minimum number of worker instances",
    )
    parser.add_argument(
        "--max-instances",
        type=int,
        metavar="N",
        default=10,
        help="Maximum number of worker instances",
    )
    parser.add_argument(
        "--throughput",
        type=int,
        metavar="N",
        default=20,
        help=f"How many calls a worker can process in {interval} seconds",
    )
    parser.add_argument(
        "--image",
        type=str,
        help="Docker image to run",
    )
    args = parser.parse_args()

    vast_api_key = os.getenv("VAST_API_KEY")
    if not vast_api_key:
        vast_api_key = open(os.path.expanduser("~/.vast_api_key")).read().strip()

    logging.info(
        f"Started autoscaler: min_instances={args.min_instances} max_instances={args.max_instances} throughput={args.throughput}"
    )

    while True:
        start = time.time()
        # If we scaled up or down previously, then wait an iteration for things to settle
        if prev_delta:
            prev_delta = 0
        else:
            try:
                prev_delta = autoscale(**vars(args))
            except Exception as e:
                logging.exception(e)
        end = time.time()
        last_sleep_duration = interval - (end - start)
        time.sleep(last_sleep_duration)
