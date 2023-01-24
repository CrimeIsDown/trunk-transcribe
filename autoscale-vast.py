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
        return os.environ["GIT_COMMIT"]
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
    query = [
        "rentable=true",
        "rented=false",
        "reliability>0.98",
        "num_gpus=1",
        "gpu_ram>=8",
        "dlperf_usd>200",
        "dph<=0.1",
        "cuda_vers>=11.7",
        "inet_up>=90",
        "inet_down>=90",
    ]

    p = subprocess.run(
        [
            "vast",
            "search",
            "offers",
            "--raw",
            "-n",  # Disable default query
            "-i",  # Interruptible
            "-o",  # Order by...
            "dph",  # $/hr
            " ".join(query),
        ],
        capture_output=True,
    )
    p.check_returncode()
    try:
        return json.loads(p.stdout)
    except json.decoder.JSONDecodeError as e:
        logging.error(p.stdout)
        raise e


def get_current_instances() -> list[dict]:
    p = subprocess.run(
        [
            "vast",
            "show",
            "instances",
            "--raw",
        ],
        capture_output=True,
    )
    p.check_returncode()
    try:
        return json.loads(p.stdout)
    except json.decoder.JSONDecodeError as e:
        logging.error(p.stdout)
        return []


def create_instance(envs: dict, image: str) -> bool:
    instance = find_available_instances()[0]

    instance_id = instance["id"]
    # Bid 1.5x the minimum bid
    bid = float(instance["dph_total"]) * 1.5

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
        "price": round(bid, 6),
        "disk": 0.5,
        "runtype": "args",
    }

    r = requests.put(
        f"https://console.vast.ai/api/v0/asks/{instance_id}/",
        params={"api_key": open(os.path.expanduser("~/.vast_api_key")).read().strip()},
        json=body,
    )
    try:
        r.raise_for_status()
        return True
    except requests.RequestException as e:
        logging.error(e)
        return False


def delete_instance() -> bool:
    deleted_running_instance = False
    deletable_instances = []

    for instance in get_current_instances():
        if instance["actual_status"] == "exited":
            deletable_instances.append(instance["id"])
        elif not deleted_running_instance:
            deletable_instances.append(instance["id"])
            deleted_running_instance = True

    if len(deletable_instances):
        for instance in deletable_instances:
            p = subprocess.run(
                ["vast", "destroy", "instance", "--raw", str(instance)],
                capture_output=True,
            )
            p.check_returncode()

    return deleted_running_instance


def autoscale(
    min_instances: int, max_instances: int, throughput: int, envs: dict, image: str
) -> int:
    queue_status = get_queue_status(envs)
    current_instances = int(queue_status["consumers"])
    past_utilization.insert(0, float(queue_status["consumer_utilisation"]))
    if len(past_utilization) > 5:
        past_utilization.pop()

    desired_instances = current_instances
    # TODO: make this a moving average/weighted average
    past_utilization_avg = mean(past_utilization)
    if past_utilization_avg < 0.9:
        message_count = queue_status["messages"]
        desired_instances += round(message_count / throughput)
    elif past_utilization_avg == 1 and queue_status["backing_queue_status"]["avg_ack_egress_rate"] > queue_status["backing_queue_status"]["avg_ack_ingress_rate"]:
        desired_instances -= 1

    scale = (
        min(max_instances, max(min_instances, desired_instances)) - current_instances
    )
    if abs(scale):
        for _ in range(abs(scale)):
            if scale > 0:
                create_instance(envs, image)
            else:
                delete_instance()

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

    envs = dotenv_values(".env.vast")

    interval = 120

    logging.info(f"Started autoscaler: min_instances={args.min_instances} max_instances={args.max_instances} throughput={args.throughput} image={args.image}")

    while True:
        start = time.time()
        result = autoscale(
            args.min_instances,
            args.max_instances,
            args.throughput,
            envs,
            args.image,
        )
        logging.info(f"Workers change: {result}")
        end = time.time()
        time.sleep(interval - (end - start))
