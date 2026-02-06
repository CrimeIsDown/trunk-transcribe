from __future__ import annotations

import datetime as dt
import os
from typing import Literal

from pydantic import BaseModel, Field, field_validator, model_validator

from app.search.helpers import encode_params, get_default_index_name


DEFAULT_MODEL = "openai:gpt-4o-mini"
DEFAULT_MAX_WINDOW_HOURS = 24
DEFAULT_MAX_HISTORY_MESSAGES = 20
DEFAULT_MAX_MESSAGE_CHARS = 4000
DEFAULT_MAX_HITS = 250
DEFAULT_MCP_TIMEOUT_SECONDS = 20


class ScannerSummaryServiceError(RuntimeError):
    pass


class ChatMessage(BaseModel):
    role: Literal["user", "assistant"]
    content: str = Field(min_length=1, max_length=DEFAULT_MAX_MESSAGE_CHARS)


class ScannerSummaryRequest(BaseModel):
    radio_channel: str = Field(min_length=1, max_length=200)
    start_datetime: dt.datetime
    end_datetime: dt.datetime
    question: str = Field(min_length=1, max_length=DEFAULT_MAX_MESSAGE_CHARS)
    history: list[ChatMessage] = Field(default_factory=list)
    radio_system: str | None = Field(default=None, max_length=120)

    @field_validator("radio_channel")
    @classmethod
    def _validate_radio_channel(cls, value: str) -> str:
        trimmed = value.strip()
        if not trimmed:
            raise ValueError("radio_channel cannot be empty")
        return trimmed

    @field_validator("radio_system")
    @classmethod
    def _validate_radio_system(cls, value: str | None) -> str | None:
        if value is None:
            return None
        trimmed = value.strip()
        return trimmed or None

    @field_validator("question")
    @classmethod
    def _validate_question(cls, value: str) -> str:
        trimmed = value.strip()
        if not trimmed:
            raise ValueError("question cannot be empty")
        return trimmed

    @field_validator("start_datetime", "end_datetime")
    @classmethod
    def _validate_timezone_aware(cls, value: dt.datetime) -> dt.datetime:
        if value.tzinfo is None or value.utcoffset() is None:
            raise ValueError("Datetime must include a timezone offset")
        return value

    @model_validator(mode="after")
    def _validate_request(self) -> "ScannerSummaryRequest":
        if self.start_datetime >= self.end_datetime:
            raise ValueError("start_datetime must be before end_datetime")

        max_window = dt.timedelta(hours=_env_int("CHAT_SUMMARY_MAX_WINDOW_HOURS", DEFAULT_MAX_WINDOW_HOURS, minimum=1))
        if self.end_datetime - self.start_datetime > max_window:
            raise ValueError(
                f"Date range exceeds maximum of {int(max_window.total_seconds() // 3600)} hours"
            )

        max_history_messages = _env_int(
            "CHAT_SUMMARY_MAX_HISTORY_MESSAGES",
            DEFAULT_MAX_HISTORY_MESSAGES,
            minimum=1,
        )
        if len(self.history) > max_history_messages:
            raise ValueError(
                f"history contains too many messages (max {max_history_messages})"
            )

        max_message_chars = _env_int(
            "CHAT_SUMMARY_MAX_MESSAGE_CHARS",
            DEFAULT_MAX_MESSAGE_CHARS,
            minimum=1,
        )
        for message in self.history:
            if len(message.content) > max_message_chars:
                raise ValueError(
                    f"history message exceeds maximum length of {max_message_chars} characters"
                )

        return self


class ScannerSummaryCitation(BaseModel):
    id: str
    start_time: str
    talkgroup_description: str
    search_url: str | None = None


class ScannerSummaryResponse(BaseModel):
    answer_markdown: str
    citations: list[ScannerSummaryCitation] = Field(default_factory=list)
    result_count: int = Field(default=0, ge=0)
    history: list[ChatMessage] = Field(default_factory=list)


class AgentCitation(BaseModel):
    id: str
    start_time: int
    talkgroup_description: str
    index_name: str | None = None


class AgentSummaryOutput(BaseModel):
    answer_markdown: str = Field(min_length=1)
    citations: list[AgentCitation] = Field(default_factory=list)
    result_count: int = Field(default=0, ge=0)


def _env_int(name: str, default: int, minimum: int = 0) -> int:
    raw = os.getenv(name)
    if raw is None:
        return default
    try:
        value = int(raw)
    except ValueError:
        return default
    return value if value >= minimum else default


def _escape_filter_value(value: str) -> str:
    return value.replace("\\", "\\\\").replace('"', '\\"')


def normalize_model_name(model_name: str) -> str:
    model_name = model_name.strip()
    if ":" in model_name:
        return model_name
    return f"openai:{model_name}"


def get_index_names_for_range(
    start_datetime: dt.datetime, end_datetime: dt.datetime
) -> list[str]:
    base_index = os.getenv("MEILI_INDEX", "calls")
    if os.getenv("MEILI_INDEX_SPLIT_BY_MONTH", "false").lower() != "true":
        return [base_index]

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


def build_citation_search_url(
    *,
    index_name: str,
    call_id: str,
    talkgroup_description: str,
    start_time_epoch: int,
) -> str | None:
    base_url = os.getenv("SEARCH_UI_URL")
    if not base_url:
        return None

    params = {
        index_name: {
            "sortBy": f"{index_name}:start_time:desc",
            "hitsPerPage": 60,
            "refinementList": {"talkgroup_description": [talkgroup_description]},
            "range": {
                "start_time": f"{start_time_epoch - 60 * 20}:{start_time_epoch + 60 * 10}"
            },
        }
    }

    return f"{base_url}?{encode_params(params)}#hit-{call_id}"


def _history_to_prompt(history: list[ChatMessage]) -> str:
    if not history:
        return "No previous chat history."
    lines = ["Prior conversation (oldest first):"]
    for message in history:
        role = "User" if message.role == "user" else "Assistant"
        lines.append(f"{role}: {message.content}")
    return "\n".join(lines)


def _build_user_prompt(request: ScannerSummaryRequest, index_names: list[str]) -> str:
    start_epoch = int(request.start_datetime.timestamp())
    end_epoch = int(request.end_datetime.timestamp())
    escaped_channel = _escape_filter_value(request.radio_channel)
    filters = [
        f'talkgroup_description = "{escaped_channel}"',
        f"start_time >= {start_epoch}",
        f"start_time <= {end_epoch}",
    ]
    if request.radio_system:
        filters.append(f'short_name = "{_escape_filter_value(request.radio_system)}"')

    index_list = "\n".join([f"- {index_name}" for index_name in index_names])
    max_hits = _env_int("CHAT_SUMMARY_MAX_HITS", DEFAULT_MAX_HITS, minimum=1)

    return "\n".join(
        [
            "Summarize recent scanner events from Meilisearch results.",
            "Use the Meilisearch MCP tools. You must perform searches before answering.",
            "Return incident digest bullets and include concrete citations.",
            "",
            f"Indexes to search:\n{index_list}",
            f"Filter expression: {' AND '.join(filters)}",
            f"Maximum hits per query: {max_hits}",
            "",
            "Output requirements:",
            "- answer_markdown: incident digest with concise bullet points.",
            "- result_count: total number of matched records used for synthesis.",
            "- citations: include at least one citation for each incident bullet when available.",
            "- Each citation must include: id, start_time (epoch seconds), talkgroup_description, and index_name.",
            "- If no matching calls are found, set result_count=0 and citations=[].",
            "",
            _history_to_prompt(request.history),
            "",
            f"Current user question: {request.question}",
        ]
    )


async def _run_agent(prompt: str, *, model_name: str) -> AgentSummaryOutput:
    try:
        from pydantic_ai import Agent
        from pydantic_ai.mcp import MCPServerStdio
    except Exception as exc:  # pragma: no cover - exercised in integration only
        raise ScannerSummaryServiceError(
            "PydanticAI MCP dependencies are not available"
        ) from exc

    meili_url = os.getenv("MEILI_URL")
    meili_master_key = os.getenv("MEILI_MASTER_KEY")
    if not meili_url or not meili_master_key:
        raise ScannerSummaryServiceError(
            "MEILI_URL and MEILI_MASTER_KEY must be configured for chat summaries"
        )

    timeout_seconds = _env_int(
        "CHAT_SUMMARY_MCP_TIMEOUT_SECONDS",
        DEFAULT_MCP_TIMEOUT_SECONDS,
        minimum=1,
    )

    mcp_server = MCPServerStdio(
        command="uvx",
        args=["-n", "meilisearch-mcp"],
        env={"MEILI_HTTP_ADDR": meili_url, "MEILI_MASTER_KEY": meili_master_key},
        timeout=timeout_seconds,
    )

    agent = Agent(
        normalize_model_name(model_name),
        output_type=AgentSummaryOutput,
        toolsets=[mcp_server],
        system_prompt=(
            "You are a public-safety scanner transcript analyst. "
            "Use only retrieved call data. Do not invent events."
        ),
    )

    try:
        if hasattr(agent, "run_mcp_servers"):
            async with agent.run_mcp_servers():
                result = await agent.run(prompt)
        else:  # pragma: no cover - compatibility fallback
            result = await agent.run(prompt)
    except Exception as exc:  # pragma: no cover - exercised in integration only
        raise ScannerSummaryServiceError(f"Failed to run scanner summary agent: {exc}") from exc

    return result.output


def _citation_index_name(citation: AgentCitation) -> str:
    if citation.index_name:
        return citation.index_name
    timestamp = dt.datetime.fromtimestamp(citation.start_time, tz=dt.timezone.utc)
    return get_default_index_name(timestamp)


async def summarize_scanner_events(
    request: ScannerSummaryRequest,
) -> ScannerSummaryResponse:
    model_name = os.getenv("CHAT_SUMMARY_MODEL", DEFAULT_MODEL)
    index_names = get_index_names_for_range(request.start_datetime, request.end_datetime)
    prompt = _build_user_prompt(request, index_names)
    output = await _run_agent(prompt, model_name=model_name)

    citations: list[ScannerSummaryCitation] = []
    for citation in output.citations:
        start_time_iso = dt.datetime.fromtimestamp(
            citation.start_time, tz=dt.timezone.utc
        ).isoformat()
        index_name = _citation_index_name(citation)
        search_url = build_citation_search_url(
            index_name=index_name,
            call_id=citation.id,
            talkgroup_description=citation.talkgroup_description,
            start_time_epoch=citation.start_time,
        )
        citations.append(
            ScannerSummaryCitation(
                id=citation.id,
                start_time=start_time_iso,
                talkgroup_description=citation.talkgroup_description,
                search_url=search_url,
            )
        )

    history = [
        *request.history,
        ChatMessage(role="user", content=request.question),
        ChatMessage(role="assistant", content=output.answer_markdown),
    ]

    return ScannerSummaryResponse(
        answer_markdown=output.answer_markdown,
        citations=citations,
        result_count=max(output.result_count, len(citations)),
        history=history,
    )
