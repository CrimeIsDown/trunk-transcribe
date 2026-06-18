from __future__ import annotations

from app.core.transcription_profiles import resolve_transcription_profile


def default_celery_queues(
    *,
    explicit_profile: str | None,
    default_profile: str | None,
    include_post_transcribe: bool = False,
) -> str:
    queues = [
        resolve_transcription_profile(
            explicit_profile=explicit_profile,
            default_profile=default_profile,
        ).queue_name
    ]
    if include_post_transcribe:
        queues.append("post_transcribe")
    return ",".join(queues)
