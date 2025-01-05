#!/usr/bin/env python3

import argparse
import json
import logging
import os
import re
import subprocess
import time
from functools import lru_cache
from http.client import HTTPConnection
from math import floor
from statistics import mean
from threading import Thread
from typing import Tuple
from urllib.parse import urlparse

import requests
import sentry_sdk
from dotenv import load_dotenv

from app import worker

load_dotenv()

sentry_dsn = os.getenv("SENTRY_DSN")
if sentry_dsn:
    sentry_sdk.init(
        dsn=sentry_dsn,
        release=os.getenv("GIT_COMMIT"),
        # Set traces_sample_rate to 1.0 to capture 100%
        # of transactions for performance monitoring.
        # We recommend adjusting this value in production.
        traces_sample_rate=float(os.getenv("SENTRY_TRACE_SAMPLE_RATE", "0.1")),
        _experiments={
            "profiles_sample_rate": float(
                os.getenv("SENTRY_PROFILE_SAMPLE_RATE", "0.1")
            ),
        },
    )


DEFAULT_MIN_INSTANCES = 1
DEFAULT_MAX_INSTANCES = 10
DEFAULT_INTERVAL = 60
FORBIDDEN_INSTANCE_CONFIG = "config/forbidden_instances.json"


class Autoscaler:
    envs: dict[str, str] = {}
    message_rates: list[float] = []
    pending_instances: dict[str, int] = {}
    forbidden_instances: set[str] = set()

    def __init__(
        self,
        min: int = DEFAULT_MIN_INSTANCES,
        max: int = DEFAULT_MAX_INSTANCES,
        interval: int = DEFAULT_INTERVAL,
        image: str | None = None,
    ):
        super().__init__()
        self.min = min
        self.max = max
        self.interval = interval

        self.vast_api_key = os.getenv("VAST_API_KEY")
        if not self.vast_api_key:
            self.vast_api_key = open(os.path.expanduser("~/.vast_api_key")).read()
        self.vast_api_key = self.vast_api_key.strip()

        self.model = os.getenv("WHISPER_MODEL", "large-v3")
        self.implementation = os.getenv("WHISPER_IMPLEMENTATION", "faster-whisper")

        # Figure out the public IP/host for external access
        hostname = urlparse(os.getenv("API_BASE_URL", "")).hostname
        if not hostname:
            hostname = requests.get("https://checkip.amazonaws.com").text.strip()

        self.envs = {
            k: v.replace("rabbitmq", hostname)
            for k, v in os.environ.items()
            if k.startswith("CELERY")
        }
        self.envs["CELERY_QUEUES"] = worker.CELERY_GPU_QUEUE

        if os.getenv("SENTRY_DSN"):
            self.envs["SENTRY_DSN"] = os.getenv("SENTRY_DSN", "")

        cuda_version = os.getenv("CUDA_VERSION", "12.1.0")
        cuda_version_matches = re.match(r"(\d+)\.(\d+)\.(\d+)", cuda_version)
        self.cuda_version = (
            f"{cuda_version_matches.group(1)}.{cuda_version_matches.group(2)}"
            if cuda_version_matches
            else "12.1"
        )

        if image:
            self.image = image
        else:
            self.image = f"ghcr.io/crimeisdown/trunk-transcribe:main-{self.implementation}-{self.model}-cuda_{cuda_version}"

        if os.path.isfile(FORBIDDEN_INSTANCE_CONFIG):
            with open(FORBIDDEN_INSTANCE_CONFIG) as config:
                self.forbidden_instances = set(json.load(config))

    def _get_image_digest(self, image: str):
        repo, tag = image.split(":", 1)
        registry, repository = repo.split("/", 1)

        r = requests.get(f"https://{registry}/token?scope=repository:{repository}:pull")
        r.raise_for_status()
        token = r.json()["token"]

        r = requests.get(
            f"https://{registry}/v2/{repository}/manifests/{tag}",
            headers={
                "Authorization": f"Bearer {token}",
                "Accept": "application/vnd.oci.image.index.v1+json",
            },
        )
        r.raise_for_status()
        digest = r.headers.get("Docker-Content-Digest")
        if digest:
            return f"{repo}@{digest}"
        raise Exception("Could not find image digest")

    def _make_instance_hostname(self, instance: dict) -> str:
        return f'{instance["machine_id"]}.{instance["host_id"]}.vast.ai'

    def _update_running_instances(self, instances: list[dict]):
        self.running_instances = [
            self._make_instance_hostname(instance)
            for instance in list(
                filter(
                    lambda i: i["actual_status"] == "running"
                    and "deletion_reason" not in i,
                    instances,
                )
            )
        ]

    def _update_pending_instances(self, instances: list[dict]):
        pending_instances = {}
        for instance in list(
            filter(
                lambda i: i["actual_status"] != "running"
                and "deletion_reason" not in i,
                instances,
            )
        ):
            hostname = None
            concurrency = 0
            for env in instance["extra_env"]:
                key = env[0]
                value = env[1]
                if key == "CELERY_HOSTNAME":
                    hostname = value
                    continue
                if key == "CELERY_CONCURRENCY":
                    concurrency = int(value)
                    continue
            if hostname and concurrency:
                pending_instances[hostname] = concurrency

        self.pending_instances = pending_instances

    def get_worker_status(self) -> list[dict]:
        workers = []
        result = worker.celery.control.inspect(timeout=10).stats()
        if result:
            for name, stats in result.items():
                workers.append({"name": name, "stats": stats})
        return workers

    def get_queue_status(self) -> dict:
        broker_api = os.getenv("FLOWER_BROKER_API")
        url = f"{broker_api}queues/%2F/{worker.CELERY_GPU_QUEUE}"
        r = requests.get(url, timeout=5)
        r.raise_for_status()
        return r.json()

    @lru_cache()
    def get_git_commit(self) -> str:
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

    def find_available_instances(self, vram_needed: float) -> list[dict]:
        vram_needed = max(10 * 1024, vram_needed)
        query = {
            "rentable": {"eq": "true"},
            "num_gpus": {"eq": "1"},
            "gpu_ram": {"gte": f"{vram_needed:.1f}"},
            "cuda_max_good": {"gte": self.cuda_version},
            "order": [["dph_total", "asc"]],
            "type": "ask" if os.getenv("VAST_ONDEMAND") else "bid",
        }

        r = requests.get(
            "https://console.vast.ai/api/v0/bundles/",
            params={"q": json.dumps(query)},
            headers={"Authorization": f"Bearer {self.vast_api_key}"},
        )
        r.raise_for_status()

        # Filter this list to exclude any instances we're already renting, and exclude non-RTX GPUs
        return list(
            filter(
                lambda offer: self._make_instance_hostname(offer)
                not in (self.running_instances + list(self.forbidden_instances))
                and "RTX" in offer["gpu_name"],
                r.json()["offers"],
            )
        )

    def get_current_instances(self) -> list[dict]:
        r = requests.get(
            "https://console.vast.ai/api/v0/instances/",
            params={"owner": "me"},
            headers={"Authorization": f"Bearer {self.vast_api_key}"},
        )
        r.raise_for_status()
        # Filter instances to those owned by this API
        instances = list(
            filter(
                lambda i: ["CELERY_BROKER_URL", self.envs["CELERY_BROKER_URL"]]
                in i["extra_env"],
                r.json()["instances"],
            )
        )
        self._update_running_instances(instances)
        self._update_pending_instances(instances)
        return instances

    def create_instances(self, count: int) -> int:
        logging.info(f"Scaling up by {count} instances")

        mem_util_factor = 1.0
        # Decrease the memory needed for certain forks
        if self.implementation in ["faster-whisper", "whisper.cpp"]:
            mem_util_factor = 0.4
        if self.implementation == "whispers2t":
            mem_util_factor = 0.5

        vram_requirements = {
            "tiny.en": 1.5 * 1024 * mem_util_factor,
            "base.en": 2 * 1024 * mem_util_factor,
            "small.en": 3.5 * 1024 * mem_util_factor,
            "medium.en": 6.5 * 1024 * mem_util_factor,
            "large": 12 * 1024 * mem_util_factor,
            "large-v2": 12 * 1024 * mem_util_factor,
            "large-v3": 12 * 1024 * mem_util_factor,
        }

        vram_required = vram_requirements[self.model]
        instances = self.find_available_instances(vram_required)

        instances_created = 0

        image = self.image
        # Try to avoid image caching if possible
        if "@" not in image:
            try:
                image = self._get_image_digest(image)
            except Exception as e:
                logging.exception(e)
                sentry_sdk.capture_exception(e)
                pass

        while count and len(instances):
            instance = instances.pop(0)
            count -= 1

            instance_id = instance["id"]

            # Adjust concurrency based on GPU RAM
            concurrency = floor(instance["gpu_ram"] / vram_required)
            self.envs["CELERY_CONCURRENCY"] = str(max(1, concurrency))

            # Set a nice hostname so we don't use a random Docker hash
            git_commit = self.get_git_commit()
            hostname = self._make_instance_hostname(instance)
            self.envs["CELERY_HOSTNAME"] = f"celery-{git_commit}@{hostname}"

            body = {
                "client_id": "me",
                "image": image,
                "args": ["worker"],
                "env": self.envs,
                "disk": 16,
                "runtype": "args",
            }

            if not os.getenv("VAST_ONDEMAND"):
                # Bid 1.25x the minimum bid
                body["price"] = max(
                    round(float(instance["dph_total"]) * 1.25, 6), 0.001
                )

            r = requests.put(
                f"https://console.vast.ai/api/v0/asks/{instance_id}/",
                headers={"Authorization": f"Bearer {self.vast_api_key}"},
                json=body,
            )
            r.raise_for_status()
            logging.info(
                f"Started instance {instance_id}, a {instance['gpu_name']} for ${instance['dph_total'] if os.getenv('VAST_ONDEMAND') else body['price']}/hr"
            )
            # Update our other vars
            self.running_instances.append(hostname)
            instances_created += 1

        return instances_created

    def delete_instances(
        self, count: int = 0, delete_exited: bool = False, delete_errored: bool = False
    ) -> int:
        instances = self.get_current_instances()
        online_workers = " ".join(
            [worker["name"] for worker in self.get_worker_status()]
        )
        deletable_instances = []
        bad_instances = []
        MAX_LOADING_DURATION = 1200

        for instance in instances:
            is_disconnected = (
                instance["actual_status"] == "running"
                and time.time() - instance["start_date"] > MAX_LOADING_DURATION + 300
                and self._make_instance_hostname(instance) not in online_workers
            )
            is_stuck = (
                instance["actual_status"] == "loading"
                and time.time() - instance["start_date"] > MAX_LOADING_DURATION
            )
            is_full = (
                instance["disk_usage"] / instance["disk_space"] > 0.9
                if instance["disk_space"]
                else False
            )
            is_errored = (
                instance["status_msg"] and "error" in instance["status_msg"].lower()
            )
            errored = delete_errored and (is_stuck or is_disconnected or is_errored)
            exited = delete_exited and (
                instance["actual_status"] == "exited"
                or instance["cur_state"] == "stopped"
            )
            if errored or exited or is_full:
                if is_disconnected:
                    instance["deletion_reason"] = "disconnected"
                if is_stuck:
                    instance["deletion_reason"] = "stuck_loading"
                if is_errored:
                    instance["deletion_reason"] = "error"
                if exited:
                    instance["deletion_reason"] = "exited"
                if is_full:
                    instance["deletion_reason"] = "disk_space_full"
                deletable_instances.append(instance)
                if is_stuck or is_errored:
                    bad_instances.append(instance)
                    self.forbidden_instances.add(self._make_instance_hostname(instance))

        if len(bad_instances):
            with open(FORBIDDEN_INSTANCE_CONFIG, "w") as config:
                json.dump(list(self.forbidden_instances), config)

        if count:
            logging.info(f"Scaling down by {count} instances")
            # Sort instance list by most expensive first, so those get deleted first
            instances = sorted(
                instances,
                key=lambda instance: instance["dph_total"],
                reverse=True,
            )
            for instance in instances:
                if count:
                    instance["deletion_reason"] = "reduce_replicas"
                    deletable_instances.append(instance)
                    count -= 1
                else:
                    break

        if len(deletable_instances):
            for instance in deletable_instances:
                r = requests.delete(
                    f"https://console.vast.ai/api/v0/instances/{instance['id']}/",
                    headers={"Authorization": f"Bearer {self.vast_api_key}"},
                    json={},
                )
                r.raise_for_status()
                age_hrs = (time.time() - instance["start_date"]) / (60 * 60)
                logging.info(
                    f"[reason: {instance['deletion_reason']}] Deleted instance {instance['id']} (a {instance['gpu_name']} for ${instance['dph_total']:.3f}/hr), was up for {age_hrs:.2f} hours. Last status: {instance['status_msg']}"
                )

        self._update_running_instances(instances)
        self._update_pending_instances(instances)

        return len(deletable_instances)

    def monitor_queue(self):
        while True:
            time.sleep(2)
            try:
                queue = self.get_queue_status()
                message_rate = (
                    queue["messages_details"]["rate"]
                    if "messages_details" in queue
                    else 0
                )
            except Exception as e:
                logging.exception(e)
                sentry_sdk.capture_exception(e)
                continue

            self.message_rates.append(message_rate)
            if len(self.message_rates) > self.interval / 2:
                self.message_rates.pop(0)

    def calculate_needed_instances(self) -> Tuple[int, int]:
        queue = self.get_queue_status()

        current_instances = queue["consumers"]

        needed_instances = current_instances

        if len(self.message_rates):
            message_rate = mean(self.message_rates)
        else:
            message_rate = queue["messages_details"]["rate"]

        logging.info(
            f"Current avg message rate: {message_rate:.2f} / Current message count: {queue['messages']} / Current instances: {current_instances}"
        )

        if message_rate > 0.4 or not queue["consumers"]:
            needed_instances += 1
        elif queue["messages"] > 400 and queue["consumers"] > 0:
            ack_rate_per_consumer = (
                queue["message_stats"]["ack_details"]["rate"] / queue["consumers"]
            )
            time_to_clear_queue = queue["messages"] / ack_rate_per_consumer
            if time_to_clear_queue > 120:
                needed_instances += 1
        elif message_rate < -0.5 and queue["messages"] < 10:
            needed_instances -= 1

        return current_instances, needed_instances

    def maybe_scale(self) -> int:
        self.delete_instances(delete_exited=True, delete_errored=True)

        current_instances, needed_instances = self.calculate_needed_instances()
        current_instances += len(self.pending_instances)

        target_instances = min(max(needed_instances, self.min), self.max)

        if target_instances > current_instances:
            return self.create_instances(target_instances - current_instances)
        if target_instances < current_instances:
            return -self.delete_instances(current_instances - target_instances)

        return 0

    def run(self):
        logging.info(
            f"Started autoscaler: min_instances={self.min} max_instances={self.max} interval={self.interval}"
        )

        # Start monitoring the queue stats
        t = Thread(target=self.monitor_queue)
        t.start()

        while True:
            start = time.time()
            try:
                change = self.maybe_scale()
                logging.info(f"Ran maybe_scale, change={change}")
            except Exception as e:
                logging.exception(e)
                sentry_sdk.capture_exception(e)
            end = time.time()
            last_sleep_duration = self.interval - (end - start)
            time.sleep(max(last_sleep_duration, 0))


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Start workers with vast.ai")
    parser.add_argument("--verbose", action="store_true", help="Enable verbose logging")
    parser.add_argument(
        "--min-instances",
        type=int,
        metavar="N",
        default=DEFAULT_MIN_INSTANCES,
        help="Minimum number of worker instances",
    )
    parser.add_argument(
        "--max-instances",
        type=int,
        metavar="N",
        default=DEFAULT_MAX_INSTANCES,
        help="Maximum number of worker instances",
    )
    parser.add_argument(
        "--interval",
        type=int,
        default=DEFAULT_INTERVAL,
        help="Interval of autoscaling loop in seconds",
    )
    parser.add_argument(
        "--image",
        type=str,
        help="Docker image to run",
    )
    args = parser.parse_args()

    if args.verbose:
        HTTPConnection.debuglevel = 2
    logging.basicConfig(
        format="[%(asctime)s] %(message)s",
        level=logging.DEBUG if args.verbose else logging.INFO,
    )

    autoscaler = Autoscaler(
        min=args.min_instances,
        max=args.max_instances,
        interval=args.interval,
        image=args.image,
    )

    autoscaler.run()
