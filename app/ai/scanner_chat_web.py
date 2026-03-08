from __future__ import annotations

from contextlib import AbstractAsyncContextManager
import datetime as dt
import json
import os
from typing import TYPE_CHECKING, Any
from urllib import error as urllib_error
from urllib import parse as urllib_parse
from urllib import request as urllib_request

from fastapi import FastAPI
from fastapi.responses import JSONResponse

if TYPE_CHECKING:
    from pydantic_ai import Agent


DEFAULT_MODEL = "openai:gpt-4o-mini"
DEFAULT_BIND_HOST = "0.0.0.0"
DEFAULT_BIND_PORT = 7932
DEFAULT_TALKGROUP_CHOICE_LIMIT = 25
DEFAULT_SEARCH_LIMIT = 20


def _env_int(name: str, default: int, minimum: int = 0) -> int:
    raw = os.getenv(name)
    if raw is None:
        return default
    try:
        value = int(raw)
    except ValueError:
        return default
    return value if value >= minimum else default


def _normalize_model_name(model_name: str) -> str:
    normalized = model_name.strip()
    if ":" in normalized:
        return normalized
    return f"openai:{normalized}"


def _index_guidance() -> str:
    base_index = os.getenv("MEILI_INDEX", "calls")
    split_by_month = os.getenv("MEILI_INDEX_SPLIT_BY_MONTH", "false").lower() == "true"
    if split_by_month:
        return (
            f"Transcript indexes are split monthly with prefix `{base_index}_YYYY_MM`."
            " If a query spans dates, search the relevant month indexes."
        )
    return f"Use Meilisearch index `{base_index}` unless the user asks for a different index."


def _default_chat_workflow() -> str:
    return "\n".join(
        [
            "Transcript search workflow:",
            "1. Before searching transcripts, determine which talkgroup tags to filter on.",
            "2. If the user did not specify exact talkgroup tags and the chat "
            "has not already confirmed them, call `get_valid_talkgroups` and ask "
            "the user to choose one or more talkgroups.",
            "3. After the user chooses talkgroups, call `search_transcripts` with "
            "those talkgroup tags so the Meilisearch tool call includes "
            "`filter` constraints.",
            "4. Never run a transcript search without a talkgroup filter unless the "
            "user explicitly asks for an all-talkgroups search.",
            "5. When the user names an imprecise or partial channel, use "
            "`get_valid_talkgroups` to confirm the exact talkgroup tags "
            "first.",
        ]
    )


def _default_system_prompt() -> str:
    return "\n".join(
        [
            "You are a scanner transcript analyst for public-safety radio traffic.",
            "Handle freeform user questions about scanner transcripts, entities, "
            "trends, timelines, and incidents.",
            "Use the provided Meilisearch tools to retrieve transcript evidence "
            "before answering factual questions.",
            "If the request is ambiguous (time range, channel, or radio system), "
            "ask a concise clarifying question.",
            "Cite concrete call IDs, talkgroups, and timestamps when you can.",
            "Never invent calls or details that are not present in retrieved data.",
            _default_chat_workflow(),
            _index_guidance(),
        ]
    )


def _default_web_instructions() -> str:
    return (
        "Ask any question about your scanner transcripts. "
        "If you do not specify talkgroups, the assistant will ask you to choose "
        "them before searching."
    )


def _escape_filter_value(value: str) -> str:
    return value.replace("\\", "\\\\").replace('"', '\\"')


def _normalize_iso_datetime(value: str | None) -> dt.datetime | None:
    if value is None:
        return None
    normalized = value.strip()
    if not normalized:
        return None
    if normalized.endswith("Z"):
        normalized = f"{normalized[:-1]}+00:00"
    parsed = dt.datetime.fromisoformat(normalized)
    if parsed.tzinfo is None or parsed.utcoffset() is None:
        return parsed.replace(tzinfo=dt.timezone.utc)
    return parsed


def _meili_config() -> tuple[str, str]:
    meili_url = os.getenv("MEILI_URL")
    meili_master_key = os.getenv("MEILI_MASTER_KEY")
    if not meili_url or not meili_master_key:
        raise RuntimeError(
            "Missing Meilisearch configuration. Set MEILI_URL and MEILI_MASTER_KEY."
        )
    return meili_url.rstrip("/"), meili_master_key


def _meili_request(
    method: str,
    path: str,
    *,
    payload: dict[str, Any] | None = None,
    query: dict[str, str] | None = None,
) -> Any:
    meili_url, meili_master_key = _meili_config()
    url = f"{meili_url}{path}"
    if query:
        url = f"{url}?{urllib_parse.urlencode(query)}"

    body = None if payload is None else json.dumps(payload).encode("utf-8")
    request = urllib_request.Request(
        url,
        method=method,
        data=body,
        headers={
            "Authorization": f"Bearer {meili_master_key}",
            "Content-Type": "application/json",
        },
    )

    try:
        with urllib_request.urlopen(request, timeout=20) as response:
            return json.loads(response.read().decode("utf-8"))
    except urllib_error.HTTPError as exc:  # pragma: no cover - network exercised in integration
        detail = exc.read().decode("utf-8")
        raise RuntimeError(f"Meilisearch request failed ({exc.code}): {detail}") from exc
    except urllib_error.URLError as exc:  # pragma: no cover - network exercised in integration
        raise RuntimeError(f"Failed to reach Meilisearch: {exc.reason}") from exc


def _get_index_names_for_range(
    start_datetime: dt.datetime | None = None,
    end_datetime: dt.datetime | None = None,
) -> list[str]:
    base_index = os.getenv("MEILI_INDEX", "calls")
    if os.getenv("MEILI_INDEX_SPLIT_BY_MONTH", "false").lower() != "true":
        return [base_index]

    if start_datetime and end_datetime:
        utc_start = start_datetime.astimezone(dt.timezone.utc).replace(
            day=1, hour=0, minute=0, second=0, microsecond=0
        )
        utc_end = end_datetime.astimezone(dt.timezone.utc).replace(
            day=1, hour=0, minute=0, second=0, microsecond=0
        )
        index_names: list[str] = []
        cursor = utc_start
        while cursor <= utc_end:
            index_names.append(f"{base_index}_{cursor.strftime('%Y_%m')}")
            if cursor.month == 12:
                cursor = cursor.replace(year=cursor.year + 1, month=1)
            else:
                cursor = cursor.replace(month=cursor.month + 1)
        return index_names

    response = _meili_request("GET", "/indexes", query={"limit": "1000"})
    results = response.get("results", [])
    matching_indexes = sorted(
        {
            index["uid"]
            for index in results
            if index.get("uid") == base_index
            or index.get("uid", "").startswith(f"{base_index}_")
        }
    )
    return matching_indexes or [base_index]


def _build_filter(
    *,
    talkgroup_tags: list[str] | None = None,
    radio_system: str | None = None,
    start_datetime: dt.datetime | None = None,
    end_datetime: dt.datetime | None = None,
) -> list[str | list[str]]:
    filters: list[str | list[str]] = []

    normalized_talkgroup_tags = [
        talkgroup_tag.strip()
        for talkgroup_tag in talkgroup_tags or []
        if talkgroup_tag and talkgroup_tag.strip()
    ]
    if normalized_talkgroup_tags:
        filters.append(
            [
                f'talkgroup_tag = "{_escape_filter_value(talkgroup_tag)}"'
                for talkgroup_tag in normalized_talkgroup_tags
            ]
        )

    normalized_system = (radio_system or "").strip()
    if normalized_system:
        filters.append(f'short_name = "{_escape_filter_value(normalized_system)}"')
    if start_datetime:
        filters.append(f"start_time >= {int(start_datetime.timestamp())}")
    if end_datetime:
        filters.append(f"start_time <= {int(end_datetime.timestamp())}")

    return filters


def _get_valid_talkgroups_from_database(
    *,
    radio_system: str | None = None,
    start_datetime: dt.datetime | None = None,
    end_datetime: dt.datetime | None = None,
    search_query: str | None = None,
    limit: int = DEFAULT_TALKGROUP_CHOICE_LIMIT,
) -> list[dict[str, str]]:
    from sqlmodel import Session

    from app.models import models
    from app.models.database import engine

    normalized_limit = max(1, min(limit, 200))
    normalized_search = (search_query or "").strip() or None

    with Session(engine) as db:
        talkgroups = models.get_talkgroups(
            db,
            radio_system=(radio_system or "").strip() or None,
            start_datetime=start_datetime,
            end_datetime=end_datetime,
            search_query=normalized_search,
            limit=normalized_limit,
        )

    return [
        {
            "short_name": str(talkgroup["short_name"]),
            "talkgroup_group": str(talkgroup["talkgroup_group"]),
            "talkgroup_tag": str(talkgroup["talkgroup_tag"]),
            "talkgroup_description": str(talkgroup["talkgroup_description"]),
            "talkgroup": str(talkgroup["talkgroup"]),
        }
        for talkgroup in talkgroups
    ]


def _search_index(
    *,
    index_name: str,
    query: str,
    filters: list[str | list[str]],
    limit: int,
) -> dict[str, Any]:
    payload: dict[str, Any] = {
        "q": query,
        "limit": limit,
        "sort": ["start_time:desc"],
        "attributesToRetrieve": [
            "id",
            "start_time",
            "short_name",
            "talkgroup",
            "talkgroup_tag",
            "talkgroup_description",
            "talkgroup_group",
            "transcript_plaintext",
            "raw_audio_url",
        ],
    }
    if filters:
        payload["filter"] = filters

    response = _meili_request(
        "POST",
        f"/indexes/{urllib_parse.quote(index_name, safe='')}/search",
        payload=payload,
    )
    hits = response.get("hits", [])
    for hit in hits:
        hit["index_name"] = index_name

    return {
        "index_name": index_name,
        "estimated_total_hits": int(response.get("estimatedTotalHits", len(hits))),
        "filter": payload.get("filter", []),
        "hits": hits,
    }


def _build_agent() -> Any:
    try:
        from pydantic_ai import Agent
    except Exception as exc:
        raise RuntimeError(
            "Missing Pydantic AI dependency. Install pydantic-ai-slim[web]."
        ) from exc
    _meili_config()

    model_name = os.getenv("CHAT_UI_MODEL") or os.getenv(
        "CHAT_SUMMARY_MODEL", DEFAULT_MODEL
    )

    system_prompt = os.getenv("CHAT_UI_SYSTEM_PROMPT", _default_system_prompt())

    agent = Agent(
        _normalize_model_name(model_name),
        instructions=system_prompt,
    )

    @agent.tool_plain
    def get_valid_talkgroups(
        radio_system: str | None = None,
        start_datetime: str | None = None,
        end_datetime: str | None = None,
        search_query: str | None = None,
        limit: int = DEFAULT_TALKGROUP_CHOICE_LIMIT,
    ) -> dict[str, Any]:
        """Return valid talkgroup choices from the database.

        Use this before asking the user to choose talkgroups when they did not specify
        an exact talkgroup tag. Apply any known radio system, time window,
        or partial query so the choices are relevant to the user's request.
        """

        start_value = _normalize_iso_datetime(start_datetime)
        end_value = _normalize_iso_datetime(end_datetime)
        choices = _get_valid_talkgroups_from_database(
            radio_system=radio_system,
            start_datetime=start_value,
            end_datetime=end_value,
            search_query=search_query,
            limit=limit,
        )

        return {
            "radio_system": (radio_system or "").strip() or None,
            "start_datetime": start_value.isoformat() if start_value else None,
            "end_datetime": end_value.isoformat() if end_value else None,
            "search_query": (search_query or "").strip() or None,
            "choices": choices,
        }

    @agent.tool_plain
    def search_transcripts(
        query: str,
        talkgroup_tags: list[str],
        radio_system: str | None = None,
        start_datetime: str | None = None,
        end_datetime: str | None = None,
        limit: int = DEFAULT_SEARCH_LIMIT,
    ) -> dict[str, Any]:
        """Search transcripts with Meilisearch filters.

        Always pass one or more exact talkgroup tags so the tool call applies
        Meilisearch `filter` constraints instead of doing a broad unfiltered search.
        """

        normalized_talkgroup_tags = [
            talkgroup_tag.strip()
            for talkgroup_tag in talkgroup_tags
            if talkgroup_tag and talkgroup_tag.strip()
        ]
        if not normalized_talkgroup_tags:
            raise ValueError("talkgroup_tags must contain at least one value")

        normalized_limit = max(1, min(limit, 50))
        start_value = _normalize_iso_datetime(start_datetime)
        end_value = _normalize_iso_datetime(end_datetime)
        filters = _build_filter(
            talkgroup_tags=normalized_talkgroup_tags,
            radio_system=radio_system,
            start_datetime=start_value,
            end_datetime=end_value,
        )

        index_names = _get_index_names_for_range(start_value, end_value)
        responses = [
            _search_index(
                index_name=index_name,
                query=query,
                filters=filters,
                limit=normalized_limit,
            )
            for index_name in index_names
        ]
        combined_hits = sorted(
            [hit for response in responses for hit in response["hits"]],
            key=lambda hit: int(hit.get("start_time", 0)),
            reverse=True,
        )[:normalized_limit]

        return {
            "query": query,
            "index_names": index_names,
            "filter": filters,
            "result_count": sum(
                int(response["estimated_total_hits"]) for response in responses
            ),
            "hits": combined_hits,
        }

    return agent


def _build_error_app(detail: str) -> FastAPI:
    app = FastAPI(title="Scanner Chat UI")

    @app.get("/api/health")
    async def health() -> JSONResponse:
        return JSONResponse(
            status_code=503,
            content={"status": "error", "detail": detail},
        )

    @app.get("/")
    async def root() -> JSONResponse:
        return JSONResponse(status_code=503, content={"detail": detail})

    return app


def _register_mcp_lifecycle(app: Any, agent: Any) -> None:
    run_mcp_servers = getattr(agent, "run_mcp_servers", None)
    if not callable(run_mcp_servers):
        return

    @app.on_event("startup")
    async def _startup() -> None:
        context_manager: AbstractAsyncContextManager[Any] = run_mcp_servers()
        app.state.mcp_context_manager = context_manager
        await context_manager.__aenter__()

    @app.on_event("shutdown")
    async def _shutdown() -> None:
        context_manager = getattr(app.state, "mcp_context_manager", None)
        if context_manager is None:
            return
        await context_manager.__aexit__(None, None, None)


def _build_app() -> tuple[Any, Any | None]:
    try:
        agent = _build_agent()
    except Exception as exc:
        return _build_error_app(str(exc)), None

    web_instructions = os.getenv("CHAT_UI_WEB_INSTRUCTIONS", _default_web_instructions())
    to_web = getattr(agent, "to_web", None)
    if callable(to_web):
        app = to_web(instructions=web_instructions)
    else:
        to_ag_ui = getattr(agent, "to_ag_ui", None)
        if not callable(to_ag_ui):
            return (
                _build_error_app(
                    "Installed pydantic-ai package does not support Agent.to_web() "
                    "or Agent.to_ag_ui()."
                ),
                None,
            )
        app = to_ag_ui()

    _register_mcp_lifecycle(app, agent)
    return app, agent


app, _agent = _build_app()


def main() -> None:
    host = os.getenv("CHAT_UI_HOST", DEFAULT_BIND_HOST)
    port = _env_int("CHAT_UI_BIND_PORT", DEFAULT_BIND_PORT, minimum=1)
    log_level = os.getenv("UVICORN_LOG_LEVEL", "info")

    import uvicorn

    uvicorn.run(
        "app.ai.scanner_chat_web:app",
        host=host,
        port=port,
        log_level=log_level,
    )


if __name__ == "__main__":
    main()
