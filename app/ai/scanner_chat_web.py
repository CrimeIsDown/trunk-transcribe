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
from pydantic import BaseModel, Field

if TYPE_CHECKING:
    from pydantic_ai import Agent


DEFAULT_MODEL = "openai:gpt-4o-mini"
DEFAULT_BIND_HOST = "0.0.0.0"
DEFAULT_BIND_PORT = 7932
DEFAULT_TALKGROUP_CHOICE_LIMIT = 25
DEFAULT_MAX_ANALYSIS_HITS = 200
DEFAULT_SEARCH_PAGE_SIZE = 50
SUPPORTED_REFINEMENT_ATTRIBUTES = {
    "radios",
    "short_name",
    "talkgroup_description",
    "talkgroup_group",
    "talkgroup_group_tag",
    "talkgroup_tag",
    "units",
}
SUPPORTED_HIERARCHICAL_ATTRIBUTES = {
    "talkgroup_hierarchy.lvl0",
    "talkgroup_hierarchy.lvl1",
    "talkgroup_hierarchy.lvl2",
}


class SearchScopeRange(BaseModel):
    start_time: str | None = None


class SearchScope(BaseModel):
    query: str | None = None
    refinementList: dict[str, list[str]] = Field(default_factory=dict)
    hierarchicalMenu: dict[str, str] = Field(default_factory=dict)
    range: SearchScopeRange | None = None
    maxHits: int | None = Field(default=None, ge=1)


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
            " Search the relevant month indexes based on the active time range."
        )
    return f"Use Meilisearch index `{base_index}` unless the user asks for a different index."


def _default_chat_workflow() -> str:
    return "\n".join(
        [
            "Transcript analysis workflow:",
            "1. If the frontend tool `get_current_search_scope` is available, call it before searching transcripts.",
            "2. Use `search_transcripts` with that exact scope so your evidence matches the visible search results.",
            "3. Only widen or change the scope if the user explicitly asks to change the search filters.",
            "4. `search_transcripts` paginates through matching results up to the configured analysis cap.",
            "5. If the user names an imprecise or partial channel and wants to refine the search, use `get_valid_talkgroups` to suggest concrete talkgroups.",
        ]
    )


def _default_system_prompt() -> str:
    return "\n".join(
        [
            "You are a scanner transcript analyst for public-safety radio traffic.",
            "Handle freeform user questions about scanner transcripts, entities, trends, timelines, and incidents.",
            "Use the provided transcript search tools to retrieve evidence before answering factual questions.",
            "Cite concrete call IDs, talkgroups, and timestamps when you can.",
            "If frontend search navigation tools are available, use them to help the user open matching search results or cited calls.",
            "Never invent calls or details that are not present in retrieved data.",
            _default_chat_workflow(),
            _index_guidance(),
        ]
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


def _parse_epoch_range(value: str | None) -> tuple[int | None, int | None]:
    if not value:
        return None, None
    start_raw, end_raw = value.split(":", 1)

    def parse_part(part: str) -> int | None:
        stripped = part.strip()
        if not stripped:
            return None
        try:
            return int(stripped)
        except ValueError:
            return None

    return parse_part(start_raw), parse_part(end_raw)


def _normalize_search_scope(scope: SearchScope | dict[str, Any] | None) -> SearchScope:
    parsed_scope = (
        SearchScope.model_validate(scope)
        if isinstance(scope, dict)
        else scope
        if isinstance(scope, SearchScope)
        else SearchScope()
    )

    query = (parsed_scope.query or "").strip() or None
    refinement_list = {
        attribute: sorted(
            {
                value.strip()
                for value in values
                if isinstance(value, str) and value.strip()
            }
        )
        for attribute, values in parsed_scope.refinementList.items()
        if attribute in SUPPORTED_REFINEMENT_ATTRIBUTES
    }
    hierarchical_menu = {
        attribute: value.strip()
        for attribute, value in parsed_scope.hierarchicalMenu.items()
        if attribute in SUPPORTED_HIERARCHICAL_ATTRIBUTES and value.strip()
    }
    range_value = (
        parsed_scope.range.start_time.strip()
        if parsed_scope.range and parsed_scope.range.start_time
        else None
    )

    return SearchScope(
        query=query,
        refinementList={
            attribute: values for attribute, values in refinement_list.items() if values
        },
        hierarchicalMenu=hierarchical_menu,
        range=SearchScopeRange(start_time=range_value) if range_value else None,
        maxHits=parsed_scope.maxHits,
    )


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


def _scope_range_datetimes(scope: SearchScope) -> tuple[dt.datetime | None, dt.datetime | None]:
    start_epoch, end_epoch = _parse_epoch_range(scope.range.start_time if scope.range else None)

    def to_datetime(value: int | None) -> dt.datetime | None:
        if value is None:
            return None
        return dt.datetime.fromtimestamp(value, tz=dt.timezone.utc)

    return to_datetime(start_epoch), to_datetime(end_epoch)


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


def _get_index_names_for_scope(scope: SearchScope) -> list[str]:
    start_datetime, end_datetime = _scope_range_datetimes(scope)
    index_names = _get_index_names_for_range(start_datetime, end_datetime)
    return list(reversed(index_names))


def _build_scope_filters(scope: SearchScope) -> list[str | list[str]]:
    filters: list[str | list[str]] = []

    for attribute in sorted(scope.refinementList):
        values = scope.refinementList[attribute]
        if values:
            filters.append(
                [
                    f'{attribute} = "{_escape_filter_value(value)}"'
                    for value in values
                ]
            )

    for attribute in sorted(scope.hierarchicalMenu):
        filters.append(
            f'{attribute} = "{_escape_filter_value(scope.hierarchicalMenu[attribute])}"'
        )

    start_epoch, end_epoch = _parse_epoch_range(scope.range.start_time if scope.range else None)
    if start_epoch is not None:
        filters.append(f"start_time >= {start_epoch}")
    if end_epoch is not None:
        filters.append(f"start_time <= {end_epoch}")

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


def _search_index_page(
    *,
    index_name: str,
    query: str,
    filters: list[str | list[str]],
    limit: int,
    offset: int,
) -> dict[str, Any]:
    payload: dict[str, Any] = {
        "q": query,
        "limit": limit,
        "offset": offset,
        "sort": ["start_time:desc"],
        "attributesToRetrieve": [
            "geo_formatted_address",
            "id",
            "radios",
            "raw_audio_url",
            "short_name",
            "start_time",
            "talkgroup",
            "talkgroup_description",
            "talkgroup_group",
            "talkgroup_group_tag",
            "talkgroup_tag",
            "transcript_plaintext",
            "units",
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
        "offset": offset,
        "limit": limit,
    }


def _resolve_max_hits(scope: SearchScope, requested_max_hits: int | None = None) -> int:
    configured_cap = _env_int(
        "CHAT_UI_MAX_ANALYSIS_HITS", DEFAULT_MAX_ANALYSIS_HITS, minimum=1
    )
    desired = requested_max_hits or scope.maxHits or configured_cap
    return max(1, min(desired, configured_cap))


def _search_transcripts_for_scope(
    scope: SearchScope | dict[str, Any] | None,
    *,
    requested_max_hits: int | None = None,
) -> dict[str, Any]:
    normalized_scope = _normalize_search_scope(scope)
    max_hits = _resolve_max_hits(normalized_scope, requested_max_hits)
    page_size = min(
        _env_int("CHAT_UI_SEARCH_PAGE_SIZE", DEFAULT_SEARCH_PAGE_SIZE, minimum=1),
        max_hits,
    )
    filters = _build_scope_filters(normalized_scope)
    query = normalized_scope.query or ""
    index_names = _get_index_names_for_scope(normalized_scope)

    estimated_total_hits = 0
    combined_hits: list[dict[str, Any]] = []
    per_index_totals: list[dict[str, Any]] = []

    for index_name in index_names:
        offset = 0
        index_total_hits = 0

        while len(combined_hits) < max_hits:
            remaining = max_hits - len(combined_hits)
            response = _search_index_page(
                index_name=index_name,
                query=query,
                filters=filters,
                limit=min(page_size, remaining),
                offset=offset,
            )
            hits = response["hits"]
            index_total_hits = response["estimated_total_hits"]

            if offset == 0:
                estimated_total_hits += index_total_hits

            if not hits:
                break

            combined_hits.extend(hits)
            offset += len(hits)

            if len(hits) < response["limit"]:
                break

        per_index_totals.append(
            {
                "index_name": index_name,
                "estimated_total_hits": index_total_hits,
            }
        )

        if len(combined_hits) >= max_hits:
            break

    return {
        "query": query,
        "index_names": index_names,
        "index_totals": per_index_totals,
        "filter": filters,
        "applied_scope": normalized_scope.model_dump(exclude_none=True),
        "estimated_total_hits": estimated_total_hits,
        "examined_hits": len(combined_hits),
        "truncated": estimated_total_hits > len(combined_hits),
        "hits": combined_hits,
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
        """Return talkgroup choices from the database for refining transcript searches."""

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
        scope: SearchScope,
        max_hits: int | None = None,
    ) -> dict[str, Any]:
        """Search transcripts using the exact active search scope and paginate up to the analysis cap."""

        return _search_transcripts_for_scope(scope, requested_max_hits=max_hits)

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

    to_ag_ui = getattr(agent, "to_ag_ui", None)
    if not callable(to_ag_ui):
        return (
            _build_error_app(
                "Installed pydantic-ai package does not support Agent.to_ag_ui()."
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
