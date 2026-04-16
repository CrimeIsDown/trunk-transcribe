from __future__ import annotations

import itertools
import logging
import os
import threading
import time
from typing import Annotated

import requests
from fastapi import FastAPI, Form, Header, HTTPException, UploadFile
from fastapi.responses import JSONResponse

from app.asr_pool.vast import VastPoolInstance, get_vast_api_key, list_vast_pool_instances

logger = logging.getLogger(__name__)

DISCOVERY_TIMEOUT_SECONDS = int(os.getenv("ASR_ROUTER_DISCOVERY_TIMEOUT_SECONDS", "10"))
UPSTREAM_REFRESH_SECONDS = int(os.getenv("ASR_ROUTER_UPSTREAM_REFRESH_SECONDS", "15"))
REQUEST_TIMEOUT_SECONDS = int(os.getenv("ASR_ROUTER_REQUEST_TIMEOUT_SECONDS", "120"))
HEALTHCHECK_PATH = os.getenv("ASR_ROUTER_HEALTHCHECK_PATH", "/v1/models")
POOL_PORT = int(os.getenv("ASR_ROUTER_INTERNAL_PORT", "8000"))
ROUTER_TARGETS = {
    item.strip() for item in os.getenv("ASR_ROUTER_ENDPOINT_TARGETS", "").split(",") if item.strip()
}

app = FastAPI()


class RouterState:
    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._rr_index = itertools.count()
        self._upstreams: dict[str, list[VastPoolInstance]] = {}
        self._unhealthy_until: dict[str, float] = {}

    def replace_upstreams(self, upstreams: dict[str, list[VastPoolInstance]]) -> None:
        with self._lock:
            self._upstreams = upstreams

    def mark_unhealthy(self, public_url: str, cooldown_seconds: int = 15) -> None:
        with self._lock:
            self._unhealthy_until[public_url] = time.time() + cooldown_seconds

    def get_upstream(self, endpoint_target: str) -> VastPoolInstance:
        with self._lock:
            choices = [
                item
                for item in self._upstreams.get(endpoint_target, [])
                if self._unhealthy_until.get(item.public_url, 0) <= time.time()
            ]
            if not choices:
                raise LookupError(endpoint_target)
            index = next(self._rr_index) % len(choices)
            return choices[index]

    def snapshot(self) -> dict[str, list[str]]:
        with self._lock:
            return {
                target: [instance.public_url for instance in instances]
                for target, instances in self._upstreams.items()
            }


state = RouterState()


def target_to_pool(endpoint_target: str) -> str:
    if not endpoint_target.startswith("pool."):
        raise ValueError(
            "ASR router only supports self-managed pool endpoint targets."
        )
    _, _, pool_name = endpoint_target.partition("pool.")
    return pool_name


def discover_upstreams() -> dict[str, list[VastPoolInstance]]:
    if not ROUTER_TARGETS:
        return {}
    upstreams: dict[str, list[VastPoolInstance]] = {}
    api_key = get_vast_api_key()
    for endpoint_target in ROUTER_TARGETS:
        pool_name = target_to_pool(endpoint_target)
        upstreams[endpoint_target] = list_vast_pool_instances(
            pool_name=pool_name,
            vast_api_key=api_key,
            healthcheck_path=HEALTHCHECK_PATH,
            internal_port=POOL_PORT,
            timeout=DISCOVERY_TIMEOUT_SECONDS,
        )
    return upstreams


def refresh_loop() -> None:
    while True:
        try:
            state.replace_upstreams(discover_upstreams())
        except Exception as exc:
            logger.exception("Failed refreshing ASR router upstreams", exc_info=exc)
        time.sleep(UPSTREAM_REFRESH_SECONDS)


@app.on_event("startup")
def startup_event() -> None:
    state.replace_upstreams(discover_upstreams())
    thread = threading.Thread(target=refresh_loop, daemon=True)
    thread.start()


@app.get("/healthz")
def healthcheck() -> JSONResponse:
    return JSONResponse({"upstreams": state.snapshot()})


@app.post("/v1/audio/transcriptions")
def route_transcription(
    file: UploadFile,
    model: Annotated[str, Form()],
    language: Annotated[str | None, Form()] = None,
    prompt: Annotated[str | None, Form()] = None,
    response_format: Annotated[str | None, Form()] = None,
    endpoint_target: Annotated[str | None, Header(alias="X-ASR-Endpoint-Target")] = None,
) -> JSONResponse:
    if not endpoint_target:
        raise HTTPException(status_code=400, detail="Missing X-ASR-Endpoint-Target header")

    try:
        upstream = state.get_upstream(endpoint_target)
    except LookupError as exc:
        raise HTTPException(
            status_code=503,
            detail=f"No healthy ASR upstreams available for {exc.args[0]}",
        ) from exc

    request_data = {
        "model": model,
        "language": language or "en",
        "prompt": prompt or "",
        "response_format": response_format or "verbose_json",
    }

    file.file.seek(0)
    try:
        response = requests.post(
            f"{upstream.public_url}/v1/audio/transcriptions",
            files={"file": (file.filename or "audio.wav", file.file, file.content_type or "application/octet-stream")},
            data=request_data,
            timeout=REQUEST_TIMEOUT_SECONDS,
        )
        response.raise_for_status()
        return JSONResponse(response.json(), status_code=response.status_code)
    except requests.RequestException as exc:
        state.mark_unhealthy(upstream.public_url)
        raise HTTPException(
            status_code=502,
            detail=f"Upstream ASR request failed for {endpoint_target}: {exc}",
        ) from exc
