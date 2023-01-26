#!/usr/bin/env python3

import argparse
import json
import logging
import os
import subprocess
import time
from functools import lru_cache
from math import floor
from statistics import mean
from urllib.parse import urlparse

import requests
from dotenv import dotenv_values
from requests.auth import HTTPBasicAuth

past_utilization = []
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
    query = {
        "rentable": {"eq": "true"},
        "rented": {"eq": "false"},
        "reliability": {"gt": "0.98"},
        "reliability2": {"gt": "0.98"},
        "num_gpus": {"eq": "1"},
        "gpu_ram": {"gt": "8000.0"},
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
    return r.json()["offers"]


def get_current_instances() -> list[dict]:
    r = requests.get(
        "https://console.vast.ai/api/v0/instances",
        params={"owner": "me", "api_key": vast_api_key},
    )
    r.raise_for_status()
    return r.json()["instances"]


def create_instances(count: int, envs: dict, image: str):
    instances = find_available_instances()

    while count and len(instances):
        instance = instances.pop(0)
        count -= 1

        instance_id = instance["id"]
        # Bid 1.5x the minimum bid
        bid = round(float(instance["dph_total"]) * 1.5, 6)

        # Adjust concurrency based on GPU RAM (assuming medium.en model)
        envs["CELERY_CONCURRENCY"] = str(floor(instance["gpu_ram"] / (7 * 1024)))

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
    min_instances: int, max_instances: int, throughput: int, image: str
) -> int:
    envs = dotenv_values(".env.vast")

    queue_status = get_queue_status(envs)
    current_instances = int(queue_status["consumers"])
    past_utilization.insert(0, float(queue_status["consumer_utilisation"]))
    if len(past_utilization) > 5:
        past_utilization.pop()

    desired_instances = current_instances
    # TODO: make this a moving average/weighted average
    past_utilization_avg = mean(past_utilization)
    if (
        past_utilization_avg < 0.9
        and queue_status["backing_queue_status"]["avg_egress_rate"]
        < queue_status["backing_queue_status"]["avg_ingress_rate"]
    ):
        message_count = queue_status["messages"]
        desired_instances += round(message_count / throughput)
    elif (
        past_utilization_avg == 1
        and queue_status["backing_queue_status"]["avg_ack_egress_rate"]
        > queue_status["backing_queue_status"]["avg_ack_ingress_rate"]
    ):
        desired_instances -= 1

    scale = (
        min(max_instances, max(min_instances, desired_instances)) - current_instances
    )
    count = abs(scale)
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
        help="How many calls a worker can process in a minute",
    )
    parser.add_argument(
        "--image",
        type=str,
        default="crimeisdown/trunk-transcribe:main-medium.en-cu117",
        help="Docker image to run",
    )
    args = parser.parse_args()

    vast_api_key = os.getenv("VAST_API_KEY")
    if not vast_api_key:
        vast_api_key = open(os.path.expanduser("~/.vast_api_key")).read().strip()

    interval = 120

    logging.info(
        f"Started autoscaler: min_instances={args.min_instances} max_instances={args.max_instances} throughput={args.throughput} image={args.image}"
    )

    while True:
        start = time.time()
        try:
            autoscale(**vars(args))
        except Exception as e:
            logging.exception(e)
        end = time.time()
        time.sleep(interval - (end - start))
