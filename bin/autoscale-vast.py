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

import requests
import sentry_sdk
from dotenv import dotenv_values, load_dotenv

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
    )


class Autoscaler:
    interval = 60
    min = 1
    max = 10
    envs: dict[str, str] = {}

    def __init__(self, min: int, max: int, image: str | None = None):
        super().__init__()
        self.min = min
        self.max = max

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
            self.image = f"crimeisdown/trunk-transcribe:main-{self.model}-cu117"

    def get_worker_status(self) -> list[dict]:
        url = f'{os.getenv("FLOWER_URL")}/api/workers'
        # Get all workers
        r = requests.get(url, params={"refresh": True}, timeout=5)
        r.raise_for_status()
        workers = r.json()
        # Get the status of each worker
        r = requests.get(url, params={"status": True}, timeout=5)
        r.raise_for_status()
        # Get the names of the online workers
        online_workers = [name for name, online in r.json().items() if online]
        # Filter our worker data to only those that are online
        return [worker for name, worker in workers.items() if name in online_workers]

    def get_queue_status(self) -> list[dict]:
        flower_baseurl = os.getenv("FLOWER_URL")
        url = f"{flower_baseurl}/api/queues/length"
        r = requests.get(url, timeout=5)
        r.raise_for_status()
        return r.json()["active_queues"]

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

    def find_available_instances(self) -> list[dict]:
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
            params={"q": json.dumps(query), "api_key": self.vast_api_key},
        )
        r.raise_for_status()

        # Filter this list to exclude any instances we're already renting
        return list(
            filter(
                lambda offer: f'{offer["host_id"]}_{offer["machine_id"]}'
                not in self.instance_ids,
                r.json()["offers"],
            )
        )

    def get_current_instances(self) -> list[dict]:
        r = requests.get(
            "https://console.vast.ai/api/v0/instances",
            params={"owner": "me", "api_key": self.vast_api_key},
        )
        r.raise_for_status()
        self.instances = r.json()["instances"]
        self.instance_ids = [
            f'{instance["host_id"]}_{instance["machine_id"]}'
            for instance in self.instances
        ]
        return self.instances

    def create_instances(self, count: int):
        logging.info(f"Scaling up by {count} instances")

        vram_requirements = {
            "tiny.en": 1.5 * 1024,
            "base.en": 2 * 1024,
            "small.en": 3.5 * 1024,
            "medium.en": 6.5 * 1024,
            "large": 12 * 1024,
        }
        vram_required = vram_requirements[self.model]
        instances = self.find_available_instances()

        while count and len(instances):
            instance = instances.pop(0)
            count -= 1

            instance_id = instance["id"]
            # Bid 1.5x the minimum bid
            bid = round(float(instance["dph_total"]) * 1.5, 6)

            # Adjust concurrency based on GPU RAM
            self.envs["CELERY_CONCURRENCY"] = str(
                floor(instance["gpu_ram"] / vram_required)
            )

            # Set a nice hostname so we don't use a random Docker hash
            git_commit = self.get_git_commit()
            self.envs["CELERY_HOSTNAME"] = f"celery-{git_commit}@vast-{instance_id}"

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

    def delete_instances(self, count: int | list[dict]):
        if isinstance(count, int):
            logging.info(f"Scaling down by {count} instances")
            deletable_instances = []

            # Sort instance list by most expensive first, so those get deleted first
            instances = sorted(
                self.get_current_instances(),
                key=lambda instance: instance["dph_total"],
                reverse=True,
            )
            for instance in instances:
                if count:
                    deletable_instances.append(instance)
                    count -= 1
        else:
            deletable_instances = count

        if len(deletable_instances):
            for instance in deletable_instances:
                r = requests.delete(
                    f"https://console.vast.ai/api/v0/instances/{instance['id']}/",
                    params={"api_key": self.vast_api_key},
                    json={},
                )
                r.raise_for_status()
                logging.info(
                    f"Deleted instance {instance['id']}, had status: {instance['status_msg']}"
                )
                # Remove the deleted instance from our list
                self.instance_ids.pop(
                    self.instance_ids.index(
                        f'{instance["host_id"]}_{instance["machine_id"]}'
                    )
                )

    def calculate_utilization(self):
        workers = self.get_worker_status()
        queues = self.get_queue_status()
        loading_instances = len(
            list(
                filter(
                    lambda i: i["cur_state"] != i["next_state"]
                    and i["next_state"] == "running",
                    self.instances,
                )
            )
        )

        max_capacity = sum(
            [worker["stats"]["pool"]["max-concurrency"] for worker in workers if "stats" in worker]
        )
        # TODO: Count loading instances based on their future concurrency instead of assuming 1
        total_capacity = max_capacity + loading_instances
        processing = sum([len(worker["active"]) for worker in workers if "active" in worker])
        queued = queues[0]["messages"] if len(queues) else 0
        jobs = processing + queued
        # Use our job count if we have no capacity to determine what to do
        utilization = jobs / total_capacity if total_capacity else jobs

        logging.debug(
            f"Calculated utilization {utilization:.2f} = {processing} active jobs + {queued} queued jobs / {max_capacity} processes + {loading_instances} pending instances"
        )

        return utilization

    def calculate_needed_instances(self, current_instances: int):
        utilization_readings = []
        while len(utilization_readings) < round(self.interval / 4):
            utilization_readings.append(self.calculate_utilization())
            time.sleep(self.interval / 30)

        avg_utilization = mean(utilization_readings)

        logging.info(f"Current average utilization: {avg_utilization:.2f}")

        if avg_utilization > 1.5:
            return current_instances + 1
        elif avg_utilization < 0.5:
            return current_instances - 1
        else:
            return current_instances

    def maybe_scale(self) -> bool:
        instances = self.get_current_instances()

        # Clean up any exited instances
        exited_instances = list(
            filter(lambda i: i["actual_status"] == "exited", instances)
        )
        if len(exited_instances):
            self.delete_instances(exited_instances)

        current_instances = len(
            list(filter(lambda i: i["next_state"] == "running", instances))
        )

        needed_instances = self.calculate_needed_instances(current_instances)

        target_instances = min(needed_instances, self.max)
        if target_instances > current_instances:
            self.create_instances(target_instances - current_instances)
            return True
        target_instances = max(needed_instances, self.min)
        if target_instances < current_instances:
            self.delete_instances(current_instances - target_instances)
            return True

        return False

    def run(self):
        logging.info(
            f"Started autoscaler: min_instances={self.min} max_instances={self.max}"
        )

        while True:
            start = time.time()
            try:
                self.maybe_scale()
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
        default=Autoscaler.min,
        help="Minimum number of worker instances",
    )
    parser.add_argument(
        "--max-instances",
        type=int,
        metavar="N",
        default=Autoscaler.max,
        help="Maximum number of worker instances",
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
        image=args.image,
    )

    autoscaler.run()
