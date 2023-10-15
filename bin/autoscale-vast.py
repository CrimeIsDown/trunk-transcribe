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
from threading import Thread

from celery import Celery
from flower.utils.broker import Broker
import requests
import sentry_sdk
from dotenv import dotenv_values, load_dotenv

load_dotenv()

# sentry_dsn = os.getenv("SENTRY_DSN")
# if sentry_dsn:
#     sentry_sdk.init(
#         dsn=sentry_dsn,
#         release=os.getenv("GIT_COMMIT"),
#         # Set traces_sample_rate to 1.0 to capture 100%
#         # of transactions for performance monitoring.
#         # We recommend adjusting this value in production.
#         traces_sample_rate=float(os.getenv("SENTRY_TRACE_SAMPLE_RATE", "0.1")),
#         _experiments={
#             "profiles_sample_rate": float(
#                 os.getenv("SENTRY_PROFILE_SAMPLE_RATE", "0.1")
#             ),
#         },
#     )


DEFAULT_MIN_INSTANCES = 1
DEFAULT_MAX_INSTANCES = 10
DEFAULT_INTERVAL = 60
FORBIDDEN_INSTANCE_CONFIG = "config/forbidden_instances.json"


class Autoscaler:
    envs: dict[str, str] = {}
    utilization_readings: list[float] = []
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
            self.vast_api_key = (
                open(os.path.expanduser("~/.vast_api_key")).read().strip()
            )

        self.envs = dotenv_values(".env.vast")  # type: ignore

        self.model = (
            self.envs["WHISPER_MODEL"]
            if "WHISPER_MODEL" in self.envs and self.envs["WHISPER_MODEL"]
            else "medium.en"
        )

        if image:
            self.image = image
        else:
            self.image = f"ghcr.io/crimeisdown/trunk-transcribe:main-{self.model}-cu117"

        if os.path.isfile(FORBIDDEN_INSTANCE_CONFIG):
            with open(FORBIDDEN_INSTANCE_CONFIG) as config:
                self.forbidden_instances = set(json.load(config))

    def _make_instance_hostname(self, instance: dict) -> str:
        return f'{instance["machine_id"]}.{instance["host_id"]}.vast.ai'

    def _update_running_instances(self, instances: list[dict]):
        self.running_instances = [
            self._make_instance_hostname(instance)
            for instance in list(
                filter(
                    lambda i: i["next_state"] == "running"
                    and "deletion_reason" not in i,
                    instances,
                )
            )
        ]

    def _get_celery_client(self) -> Celery:
        broker_url = os.getenv("CELERY_BROKER_URL")
        result_backend = os.getenv("CELERY_RESULT_BACKEND")
        return Celery(
            "worker",
            broker=broker_url,
            backend=result_backend,
            task_cls="app.whisper:WhisperTask",
            task_acks_late=True,
            worker_cancel_long_running_tasks_on_connection_loss=True,
            worker_prefetch_multiplier=1,
            timezone="UTC",
        )

    def get_worker_status(self) -> list[dict]:
        workers = []
        result = self._get_celery_client().control.inspect(timeout=10).stats().items()
        if result:
            for name, stats in result.items():
                # If this was one of our pending instances, remove it from the list
                if name in self.pending_instances:
                    del self.pending_instances[name]
                worker = {"name": name, "stats": stats}
                workers.append(worker)
        return workers

    def get_queue_status(self) -> dict:
        broker_api = os.getenv("FLOWER_BROKER_API")
        url = f"{broker_api}queues/%2F/transcribe"
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
            "dlperf": {"gt": "5"},
            "dph_total": {"lte": "0.1"},
            "cuda_vers": {"gte": "11.7"},
            "cuda_max_good": {"gte": "11.7"},
            "order": [["dph_total", "asc"]],
            "type": "bid",
        }

        r = requests.get(
            "https://console.vast.ai/api/v0/bundles",
            params={"q": json.dumps(query), "api_key": self.vast_api_key},
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
            "https://console.vast.ai/api/v0/instances",
            params={"owner": "me", "api_key": self.vast_api_key},
        )
        r.raise_for_status()
        instances = r.json()["instances"]
        self._update_running_instances(instances)
        return instances

    def create_instances(self, count: int) -> int:
        logging.info(f"Scaling up by {count} instances")

        utilization_factor = 1
        # Decrease the memory needed for certain forks
        if os.getenv("DESIRED_CUDA") == "fw" or os.getenv("DESIRED_CUDA") == "cpu-cpp":
            utilization_factor = 0.4

        vram_requirements = {
            "tiny.en": 1.5 * 1024 * utilization_factor,
            "base.en": 2 * 1024 * utilization_factor,
            "small.en": 3.5 * 1024 * utilization_factor,
            "medium.en": 6.5 * 1024 * utilization_factor,
            "large": 12 * 1024 * utilization_factor,
            "large-v2": 12 * 1024 * utilization_factor,
        }

        vram_required = vram_requirements[self.model]
        instances = self.find_available_instances(vram_required)

        instances_created = 0

        while count and len(instances):
            instance = instances.pop(0)
            count -= 1

            instance_id = instance["id"]
            # Bid 1.25x the minimum bid
            bid = round(float(instance["dph_total"]) * 1.25, 6)

            # Adjust concurrency based on GPU RAM
            concurrency = floor(instance["gpu_ram"] / vram_required)
            self.envs["CELERY_CONCURRENCY"] = str(max(1, concurrency))

            # Set a nice hostname so we don't use a random Docker hash
            git_commit = self.get_git_commit()
            hostname = self._make_instance_hostname(instance)
            self.envs["CELERY_HOSTNAME"] = f"celery-{git_commit}@{hostname}"

            body = {
                "client_id": "me",
                "image": self.image,
                "args": ["worker"],
                "env": self.envs,
                "price": bid,
                "disk": 0.5,
                "runtype": "args",
            }

            r = requests.put(
                f"https://console.vast.ai/api/v0/asks/{instance_id}/",
                params={"api_key": self.vast_api_key},
                json=body,
            )
            r.raise_for_status()
            logging.info(
                f"Started instance {instance_id}, a {instance['gpu_name']} for ${bid}/hr"
            )
            # Add the instance to our list of pending instances so we can check when it comes online
            self.pending_instances[self.envs["CELERY_HOSTNAME"]] = concurrency
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

        for instance in instances:
            is_disconnected = (
                instance["actual_status"] == "running"
                and time.time() - instance["start_date"] > 1200
                and self._make_instance_hostname(instance) not in online_workers
            )
            is_stuck = (
                instance["actual_status"] == "loading"
                and time.time() - instance["start_date"] > 900
            )
            is_errored = (
                instance["status_msg"] and "error" in instance["status_msg"].lower()
            )
            errored = delete_errored and (is_stuck or is_disconnected or is_errored)
            exited = delete_exited and (
                instance["actual_status"] == "exited"
                or instance["cur_state"] == "stopped"
            )
            if errored or exited:
                if is_disconnected:
                    instance["deletion_reason"] = "disconnected"
                if is_stuck:
                    instance["deletion_reason"] = "stuck_loading"
                if is_errored:
                    instance["deletion_reason"] = "error"
                if exited:
                    instance["deletion_reason"] = "exited"
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
            for i in range(len(instances)):
                if count:
                    instance = instances.pop(i)
                    instance["deletion_reason"] = "reduce_replicas"
                    deletable_instances.append(instance)
                    count -= 1
                else:
                    break

        if len(deletable_instances):
            for instance in deletable_instances:
                r = requests.delete(
                    f"https://console.vast.ai/api/v0/instances/{instance['id']}/",
                    params={"api_key": self.vast_api_key},
                    json={},
                )
                r.raise_for_status()
                age_hrs = (time.time() - instance["start_date"]) / (60 * 60)
                logging.info(
                    f"[reason: {instance['deletion_reason']}] Deleted instance {instance['id']} (a {instance['gpu_name']} for ${instance['dph_total']:.3f}/hr), was up for {age_hrs:.2f} hours. Last status: {instance['status_msg']}"
                )

        self._update_running_instances(instances)

        return len(deletable_instances)

    def calculate_utilization(self):
        workers = self.get_worker_status()
        queue = self.get_queue_status()

        # Calculate the total number of worker processes online
        max_capacity = sum(
            [
                worker["stats"]["pool"]["max-concurrency"]
                for worker in workers
                if "stats" in worker
            ]
        )
        # Calculate the total number of worker processes we will be creating
        pending_capacity = sum(self.pending_instances.values())
        total_capacity = max_capacity + pending_capacity
        queued = queue["messages"] if "messages" in queue else 0
        # Use our job count if we have no capacity to determine what to do
        utilization = queued / total_capacity if total_capacity else queued

        logging.debug(
            f"Calculated utilization {utilization:.2f} = {queued} queued jobs / {max_capacity} processes + {pending_capacity} pending processes"
        )

        return utilization

    def monitor_utilization(self):
        while True:
            time.sleep(2)
            try:
                current_utilization = self.calculate_utilization()
            except Exception as e:
                logging.exception(e)
                sentry_sdk.capture_exception(e)
                continue

            self.utilization_readings.append(current_utilization)
            if len(self.utilization_readings) > self.interval / 2:
                self.utilization_readings.pop(0)

    def calculate_needed_instances(self, current_instances: int):
        needed_instances = current_instances

        if len(self.utilization_readings):
            avg_utilization = mean(self.utilization_readings)

            logging.info(f"Current average utilization: {avg_utilization:.2f}")

            if avg_utilization > 2:
                needed_instances += 1
            elif avg_utilization < 0.35:
                needed_instances -= 1

        return needed_instances

    def maybe_scale(self) -> int:
        self.delete_instances(delete_exited=True, delete_errored=True)

        current_instances = len(self.running_instances)

        needed_instances = self.calculate_needed_instances(current_instances)
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

        # Start monitoring the utilization
        t = Thread(target=self.monitor_utilization)
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

    logging.basicConfig(level=logging.DEBUG if args.verbose else logging.INFO)

    autoscaler = Autoscaler(
        min=args.min_instances,
        max=args.max_instances,
        interval=args.interval,
        image=args.image,
    )

    autoscaler.run()
