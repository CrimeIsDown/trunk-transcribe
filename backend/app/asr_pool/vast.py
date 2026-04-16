from __future__ import annotations

import os
from dataclasses import dataclass

import requests


def parse_extra_env(extra_env: list[list[str]] | None) -> dict[str, str]:
    parsed: dict[str, str] = {}
    for item in extra_env or []:
        if len(item) != 2:
            continue
        parsed[str(item[0])] = str(item[1])
    return parsed


@dataclass(frozen=True)
class VastPoolInstance:
    id: int
    pool_name: str
    public_url: str
    health_url: str
    hourly_cost: float
    actual_status: str
    status_msg: str | None
    start_date: float
    extra_env: dict[str, str]
    raw: dict


def _resolve_instance_public_url(instance: dict, internal_port: int) -> str | None:
    extra_env = parse_extra_env(instance.get("extra_env"))
    if extra_env.get("ASR_PUBLIC_URL"):
        return extra_env["ASR_PUBLIC_URL"].rstrip("/")

    public_ip = instance.get("public_ipaddr") or instance.get("ssh_host")
    ports = instance.get("ports") or {}
    if not public_ip:
        return None

    port_key = f"{internal_port}/tcp"
    bindings = ports.get(port_key) or []
    host_port = None
    if bindings:
        binding = bindings[0]
        host_port = (
            binding.get("HostPort")
            or binding.get("HostPortEnd")
            or binding.get("public_port")
        )
    elif internal_port in (80, 443):
        host_port = internal_port

    if not host_port:
        return None

    scheme = "https" if str(host_port) == "443" else "http"
    return f"{scheme}://{public_ip}:{host_port}"


def list_vast_pool_instances(
    *,
    pool_name: str,
    vast_api_key: str,
    healthcheck_path: str,
    internal_port: int,
    timeout: int = 10,
) -> list[VastPoolInstance]:
    response = requests.get(
        "https://console.vast.ai/api/v0/instances/",
        params={"owner": "me"},
        headers={"Authorization": f"Bearer {vast_api_key}"},
        timeout=timeout,
    )
    response.raise_for_status()

    instances: list[VastPoolInstance] = []
    for instance in response.json().get("instances", []):
        extra_env = parse_extra_env(instance.get("extra_env"))
        if extra_env.get("ASR_POOL") != pool_name:
            continue

        public_url = _resolve_instance_public_url(instance, internal_port)
        if not public_url:
            continue

        instances.append(
            VastPoolInstance(
                id=int(instance["id"]),
                pool_name=pool_name,
                public_url=public_url,
                health_url=f"{public_url}{healthcheck_path}",
                hourly_cost=float(instance.get("dph_total") or 0.0),
                actual_status=str(instance.get("actual_status") or ""),
                status_msg=instance.get("status_msg"),
                start_date=float(instance.get("start_date") or 0),
                extra_env=extra_env,
                raw=instance,
            )
        )
    return instances


def get_vast_api_key() -> str:
    api_key = os.getenv("VAST_API_KEY")
    if api_key:
        return api_key.strip()
    with open(os.path.expanduser("~/.vast_api_key")) as file:
        return file.read().strip()
