#!/usr/bin/env python3

import argparse
import functools
import json
import logging
import math
import os
import re
import time
from http.client import HTTPConnection
from threading import Thread

import requests
import sentry_sdk
from dotenv import load_dotenv

from app.asr_pool.vast import get_vast_api_key, list_vast_pool_instances
from app.core.transcription_profiles import resolve_transcription_profile

load_dotenv()

sentry_dsn = os.getenv("SENTRY_DSN")
if sentry_dsn:
    sentry_sdk.init(
        dsn=sentry_dsn,
        release=os.getenv("GIT_COMMIT"),
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
DEFAULT_TARGET_MESSAGES_PER_INSTANCE = 4
PASSTHROUGH_ENV_PREFIXES = (
    "ASR_",
    "CUDA_",
    "HF_",
    "SENTRY_",
    "VLLM_",
    "WHISPER_",
)
PASSTHROUGH_ENV_NAMES = {"GIT_COMMIT"}

http = requests.Session()
http.request = functools.partial(http.request, timeout=10)  # type: ignore


class PoolAutoscaler:
    envs: dict[str, str] = {}
    message_rates: list[float] = []

    def __init__(
        self,
        min_instances: int = DEFAULT_MIN_INSTANCES,
        max_instances: int = DEFAULT_MAX_INSTANCES,
        interval: int = DEFAULT_INTERVAL,
        image: str | None = None,
    ):
        self.min = min_instances
        self.max = max_instances
        self.interval = interval
        self.vast_api_key = get_vast_api_key()

        profile = resolve_transcription_profile(
            explicit_profile=os.getenv("AUTOSCALE_TRANSCRIPTION_PROFILE")
            or os.getenv("TRANSCRIPTION_PROFILE"),
            default_profile=os.getenv("DEFAULT_TRANSCRIPTION_PROFILE"),
        )
        if profile.kind != "pool":
            raise RuntimeError("The Vast autoscaler only supports pool transcription profiles.")

        self.profile = profile
        self.pool_name = (
            os.getenv("AUTOSCALE_ASR_POOL")
            or profile.asr_pool
            or os.getenv("ASR_POOL")
            or "local.whisper.large-v3"
        )
        self.queue_name = os.getenv("AUTOSCALE_QUEUE_NAME") or profile.queue_name
        self.healthcheck_path = os.getenv("AUTOSCALE_HEALTHCHECK_PATH", "/v1/models")
        self.internal_port = int(os.getenv("AUTOSCALE_INTERNAL_PORT", "8000"))
        self.target_messages_per_instance = int(
            os.getenv(
                "AUTOSCALE_TARGET_MESSAGES_PER_INSTANCE",
                str(DEFAULT_TARGET_MESSAGES_PER_INSTANCE),
            )
        )
        self.boot_timeout_seconds = int(
            os.getenv("AUTOSCALE_BOOT_TIMEOUT_SECONDS", "1200")
        )
        self.template_hash = os.getenv("AUTOSCALE_TEMPLATE_HASH")
        self.image = image or os.getenv("AUTOSCALE_INSTANCE_IMAGE") or os.getenv(
            "AUTOSCALE_WORKER_IMAGE"
        )
        self.instance_args = json.loads(os.getenv("AUTOSCALE_INSTANCE_ARGS_JSON", "[]"))
        self.search_params = self._load_search_params()
        self.autoscale_gpu_ram_mb = int(os.getenv("AUTOSCALE_GPU_RAM_MB", "0") or "0")

        self.envs = {
            k: v
            for k, v in os.environ.items()
            if k.startswith(PASSTHROUGH_ENV_PREFIXES) or k in PASSTHROUGH_ENV_NAMES
        }
        self.envs["ASR_POOL"] = self.pool_name
        self.envs["ASR_VARIANT"] = profile.variant or ""

        cuda_version = os.getenv("CUDA_VERSION", "12.1.0")
        cuda_version_matches = re.match(r"(\d+)\.(\d+)\.(\d+)", cuda_version)
        self.cuda_version = (
            f"{cuda_version_matches.group(1)}.{cuda_version_matches.group(2)}"
            if cuda_version_matches
            else "12.1"
        )

    def _load_search_params(self) -> dict:
        if os.getenv("AUTOSCALE_SEARCH_PARAMS"):
            return json.loads(os.getenv("AUTOSCALE_SEARCH_PARAMS", "{}"))
        query = {
            "rentable": {"eq": "true"},
            "num_gpus": {"eq": "1"},
            "cuda_max_good": {"gte": self.cuda_version},
            "order": [["dph_total", "asc"]],
            "type": "ask" if os.getenv("VAST_ONDEMAND") else "bid",
        }
        if self.autoscale_gpu_ram_mb:
            query["gpu_ram"] = {"gte": f"{float(self.autoscale_gpu_ram_mb):.1f}"}
        return query

    def get_queue_status(self) -> dict:
        broker_api = os.getenv("FLOWER_BROKER_API")
        response = http.get(f"{broker_api}queues/%2F/{self.queue_name}")
        response.raise_for_status()
        return response.json()

    def list_instances(self):
        return list_vast_pool_instances(
            pool_name=self.pool_name,
            vast_api_key=self.vast_api_key,
            healthcheck_path=self.healthcheck_path,
            internal_port=self.internal_port,
        )

    def ready_instances(self):
        ready = []
        for instance in self.list_instances():
            if instance.actual_status != "running":
                continue
            try:
                response = http.get(instance.health_url)
                response.raise_for_status()
                ready.append(instance)
            except requests.RequestException:
                continue
        return ready

    def pending_instances(self):
        return [
            instance
            for instance in self.list_instances()
            if instance.actual_status != "running"
        ]

    def find_available_instances(self) -> list[dict]:
        response = http.get(
            "https://console.vast.ai/api/v0/bundles/",
            params={"q": json.dumps(self.search_params)},
            headers={"Authorization": f"Bearer {self.vast_api_key}"},
        )
        response.raise_for_status()

        current_hosts = {
            f"{instance.raw['machine_id']}.{instance.raw['host_id']}.vast.ai"
            for instance in self.list_instances()
            if instance.raw.get("machine_id") and instance.raw.get("host_id")
        }
        offers = []
        for offer in response.json().get("offers", []):
            host = f"{offer['machine_id']}.{offer['host_id']}.vast.ai"
            if host in current_hosts:
                continue
            offers.append(offer)
        return offers

    def create_instances(self, count: int) -> int:
        logging.info("Scaling pool %s up by %s instances", self.pool_name, count)
        offers = self.find_available_instances()
        created = 0

        while count and offers:
            offer = offers.pop(0)
            count -= 1
            ask_id = offer["id"]
            body: dict[str, object] = {
                "client_id": "me",
                "env": self.envs,
                "disk": int(os.getenv("AUTOSCALE_DISK_GB", "16")),
                "runtype": "args",
            }
            if self.template_hash:
                body["template_hash_id"] = self.template_hash
            else:
                if not self.image:
                    raise RuntimeError(
                        "Set AUTOSCALE_TEMPLATE_HASH or AUTOSCALE_INSTANCE_IMAGE."
                    )
                body["image"] = self.image
                if self.instance_args:
                    body["args"] = self.instance_args

            if not os.getenv("VAST_ONDEMAND"):
                body["price"] = max(round(float(offer["dph_total"]) * 1.25, 6), 0.001)

            response = http.put(
                f"https://console.vast.ai/api/v0/asks/{ask_id}/",
                headers={"Authorization": f"Bearer {self.vast_api_key}"},
                json=body,
            )
            response.raise_for_status()
            created += 1
            logging.info(
                "Started pool instance %s for pool=%s gpu=%s",
                ask_id,
                self.pool_name,
                offer.get("gpu_name"),
            )
        return created

    def delete_instances(self, count: int = 0, delete_unhealthy: bool = False) -> int:
        instances = self.list_instances()
        deletable = []
        now = time.time()

        if delete_unhealthy:
            for instance in instances:
                is_stuck = (
                    instance.actual_status == "loading"
                    and now - instance.start_date > self.boot_timeout_seconds
                )
                is_errored = bool(
                    instance.status_msg and "error" in instance.status_msg.lower()
                )
                if is_stuck or is_errored:
                    deletable.append(instance)

        if count:
            healthy_running = [
                instance
                for instance in instances
                if instance.actual_status == "running"
                and instance not in deletable
            ]
            healthy_running.sort(key=lambda item: item.hourly_cost, reverse=True)
            deletable.extend(healthy_running[:count])

        deleted = 0
        for instance in deletable:
            response = http.delete(
                f"https://console.vast.ai/api/v0/instances/{instance.id}/",
                headers={"Authorization": f"Bearer {self.vast_api_key}"},
                json={},
            )
            response.raise_for_status()
            deleted += 1
            logging.info(
                "Deleted pool instance %s from pool=%s status=%s",
                instance.id,
                self.pool_name,
                instance.actual_status,
            )
        return deleted

    def monitor_queue(self):
        while True:
            time.sleep(2)
            try:
                queue = self.get_queue_status()
                rate = queue.get("messages_details", {}).get("rate", 0)
            except Exception as exc:
                logging.exception(exc)
                sentry_sdk.capture_exception(exc)
                continue
            self.message_rates.append(rate)
            if len(self.message_rates) > self.interval / 2:
                self.message_rates.pop(0)

    def calculate_needed_instances(self) -> tuple[int, int]:
        queue = self.get_queue_status()
        ready = len(self.ready_instances())
        pending = len(self.pending_instances())
        messages = int(queue.get("messages") or 0)
        needed = max(self.min, math.ceil(messages / self.target_messages_per_instance))
        if messages > 0 and ready + pending == 0:
            needed = max(needed, 1)
        logging.info(
            "pool=%s queue=%s messages=%s ready=%s pending=%s target=%s",
            self.pool_name,
            self.queue_name,
            messages,
            ready,
            pending,
            needed,
        )
        return ready + pending, min(max(needed, self.min), self.max)

    def maybe_scale(self) -> int:
        self.delete_instances(delete_unhealthy=True)
        active_instances, target_instances = self.calculate_needed_instances()
        if target_instances > active_instances:
            return self.create_instances(target_instances - active_instances)
        if target_instances < active_instances:
            return -self.delete_instances(active_instances - target_instances)
        return 0

    def run(self):
        logging.info(
            "Started pool autoscaler: pool=%s queue=%s min=%s max=%s interval=%s",
            self.pool_name,
            self.queue_name,
            self.min,
            self.max,
            self.interval,
        )
        thread = Thread(target=self.monitor_queue, daemon=True)
        thread.start()

        while True:
            start = time.time()
            try:
                change = self.maybe_scale()
                logging.info("Ran maybe_scale, change=%s", change)
            except Exception as exc:
                logging.exception(exc)
                sentry_sdk.capture_exception(exc)
            sleep_duration = self.interval - (time.time() - start)
            time.sleep(max(sleep_duration, 0))


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Scale a Vast.ai ASR pool")
    parser.add_argument("--verbose", action="store_true", help="Enable verbose logging")
    parser.add_argument(
        "--min-instances",
        type=int,
        metavar="N",
        default=DEFAULT_MIN_INSTANCES,
        help="Minimum number of pool instances",
    )
    parser.add_argument(
        "--max-instances",
        type=int,
        metavar="N",
        default=DEFAULT_MAX_INSTANCES,
        help="Maximum number of pool instances",
    )
    parser.add_argument(
        "--interval",
        type=int,
        default=DEFAULT_INTERVAL,
        help="Interval of autoscaling loop in seconds",
    )
    parser.add_argument("--image", type=str, help="Container image to run")
    args = parser.parse_args()

    if args.verbose:
        HTTPConnection.debuglevel = 2
    logging.basicConfig(
        format="[%(asctime)s] %(message)s",
        level=logging.DEBUG if args.verbose else logging.INFO,
    )

    autoscaler = PoolAutoscaler(
        min_instances=args.min_instances,
        max_instances=args.max_instances,
        interval=args.interval,
        image=args.image,
    )
    autoscaler.run()
