from __future__ import annotations

import os
import re
from dataclasses import dataclass
from typing import Literal

PROFILE_KINDS = ("vendor", "pool")
REMOTE_VENDOR_QUEUE = "transcribe.remote.vendor"
POST_TRANSCRIBE_QUEUE = "post_transcribe"
DEFAULT_OPENAI_BASE_URL = "https://api.openai.com/v1"
DEFAULT_DEEPINFRA_BASE_URL = "https://api.deepinfra.com/v1/openai"


def slug_token(value: str) -> str:
    value = value.strip().lower()
    value = re.sub(r"[^a-z0-9]+", "-", value)
    return value.strip("-")


def parse_profile_string(value: str) -> dict[str, str]:
    data: dict[str, str] = {}
    for segment in value.split(";"):
        part = segment.strip()
        if not part:
            continue
        key, separator, raw = part.partition("=")
        if not separator:
            raise ValueError(
                f"Invalid transcription profile segment {part!r}. Use key=value pairs."
            )
        key = key.strip()
        raw = raw.strip()
        if not key or not raw:
            raise ValueError(
                f"Invalid transcription profile segment {part!r}. Use key=value pairs."
            )
        data[key] = raw
    return data


@dataclass(frozen=True)
class TranscriptionProfile:
    kind: Literal["vendor", "pool"]
    provider: str
    model: str
    platform: str | None = None
    family: str | None = None
    variant: str | None = None

    @classmethod
    def parse(cls, value: str) -> "TranscriptionProfile":
        data = parse_profile_string(value)
        kind = data.get("kind")
        if kind not in PROFILE_KINDS:
            supported = ", ".join(PROFILE_KINDS)
            raise ValueError(
                f"Unsupported transcription profile kind {kind!r}. Supported values: {supported}"
            )

        provider = data.get("provider")
        model = data.get("model")
        if not provider or not model:
            raise ValueError(
                "Transcription profile must include provider and model fields."
            )

        if kind == "vendor":
            return cls(kind="vendor", provider=provider, model=model)

        platform = data.get("platform")
        family = data.get("family")
        variant = data.get("variant")
        if not platform or not family or not variant:
            raise ValueError(
                "Pool transcription profiles must include platform, family, and variant fields."
            )
        return cls(
            kind="pool",
            provider=provider,
            model=model,
            platform=platform,
            family=family,
            variant=variant,
        )

    @property
    def canonical(self) -> str:
        parts = [
            f"kind={self.kind}",
            f"provider={self.provider}",
            f"model={self.model}",
        ]
        if self.kind == "pool":
            parts.extend(
                [
                    f"platform={self.platform}",
                    f"family={self.family}",
                    f"variant={self.variant}",
                ]
            )
        return ";".join(parts)

    @property
    def endpoint_target(self) -> str:
        if self.kind == "vendor":
            return f"vendor.{slug_token(self.provider)}"
        return ".".join(
            [
                "pool",
                slug_token(self.platform or ""),
                slug_token(self.family or ""),
                slug_token(self.variant or ""),
            ]
        )

    @property
    def asr_pool(self) -> str | None:
        if self.kind != "pool":
            return None
        return ".".join(
            [
                slug_token(self.platform or ""),
                slug_token(self.family or ""),
                slug_token(self.variant or ""),
            ]
        )

    @property
    def queue_name(self) -> str:
        if self.kind == "vendor":
            return REMOTE_VENDOR_QUEUE
        return ".".join(
            [
                "transcribe",
                "remote",
                "pool",
                slug_token(self.platform or ""),
                slug_token(self.family or ""),
                slug_token(self.variant or ""),
            ]
        )


def build_vendor_profile(provider: str, model: str) -> str:
    return f"kind=vendor;provider={provider};model={model}"


def build_pool_profile(
    *,
    platform: str,
    family: str,
    variant: str,
    provider: str,
    model: str,
) -> str:
    return (
        f"kind=pool;platform={platform};family={family};variant={variant};"
        f"provider={provider};model={model}"
    )


def infer_profile_from_legacy_env(
    explicit_profile: str | None = None,
    default_profile: str | None = None,
) -> str:
    if explicit_profile:
        return explicit_profile
    if default_profile:
        return default_profile

    provider = os.getenv("ASR_PROVIDER")
    model = os.getenv("ASR_MODEL") or os.getenv("WHISPER_MODEL")
    backend = os.getenv("TRANSCRIPTION_BACKEND")
    whisper_implementation = os.getenv("WHISPER_IMPLEMENTATION")

    if whisper_implementation == "openai":
        return build_vendor_profile("openai", "whisper-1")
    if whisper_implementation == "deepinfra":
        return build_vendor_profile(
            "deepinfra", model or "openai/whisper-large-v3-turbo"
        )

    family = backend or "whisper"
    platform = "local"
    variant = os.getenv("ASR_VARIANT") or ("large-v3" if family == "whisper" else family)

    if provider == "speaches" and not model:
        model = "Systran/faster-whisper-large-v3"
    if not provider:
        provider = {
            "whisper": "speaches",
            "qwen": "vllm",
            "voxtral": "voxtral",
        }.get(family, "speaches")
    if not model:
        model = {
            "whisper": "Systran/faster-whisper-large-v3",
            "qwen": "qwen2.5-omni",
            "voxtral": "mistralai/Voxtral-Mini-4B-Realtime-2602",
        }.get(family, family)
    return build_pool_profile(
        platform=platform,
        family=family,
        variant=variant,
        provider=provider,
        model=model,
    )


def resolve_transcription_profile(
    explicit_profile: str | None = None,
    default_profile: str | None = None,
) -> TranscriptionProfile:
    return TranscriptionProfile.parse(
        infer_profile_from_legacy_env(explicit_profile, default_profile)
    )
