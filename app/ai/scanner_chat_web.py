from __future__ import annotations

from contextlib import AbstractAsyncContextManager
import os
from typing import Any

from fastapi import FastAPI
from fastapi.responses import JSONResponse
from pydantic_ai import Agent
from pydantic_ai.mcp import MCPServerStdio


DEFAULT_MODEL = "openai:gpt-4o-mini"
DEFAULT_MCP_TIMEOUT_SECONDS = 20
DEFAULT_BIND_HOST = "0.0.0.0"
DEFAULT_BIND_PORT = 7932


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


def _default_system_prompt() -> str:
    return "\n".join(
        [
            "You are a scanner transcript analyst for public-safety radio traffic.",
            "Handle freeform user questions about scanner transcripts, entities, trends, timelines, and incidents.",
            "Use Meilisearch MCP tools to retrieve transcript evidence before answering factual questions.",
            "If the request is ambiguous (time range, channel, or radio system), ask a concise clarifying question.",
            "Cite concrete call IDs, talkgroups, and timestamps when you can.",
            "Never invent calls or details that are not present in retrieved data.",
            _index_guidance(),
        ]
    )


def _default_web_instructions() -> str:
    return (
        "Ask any question about your scanner transcripts. "
        "You can ask broad questions in plain English; include channel/system/time details when you want tighter results."
    )


def _build_agent() -> Agent[None, str]:
    meili_url = os.getenv("MEILI_URL")
    meili_master_key = os.getenv("MEILI_MASTER_KEY")
    if not meili_url or not meili_master_key:
        raise RuntimeError(
            "Missing Meilisearch configuration. Set MEILI_URL and MEILI_MASTER_KEY."
        )

    model_name = os.getenv("CHAT_UI_MODEL") or os.getenv(
        "CHAT_SUMMARY_MODEL", DEFAULT_MODEL
    )
    timeout_seconds = _env_int(
        "CHAT_SUMMARY_MCP_TIMEOUT_SECONDS",
        DEFAULT_MCP_TIMEOUT_SECONDS,
        minimum=1,
    )

    mcp_server = MCPServerStdio(
        command="meilisearch-mcp",
        args=[],
        env={"MEILI_HTTP_ADDR": meili_url, "MEILI_MASTER_KEY": meili_master_key},
        timeout=timeout_seconds,
    )

    system_prompt = os.getenv("CHAT_UI_SYSTEM_PROMPT", _default_system_prompt())

    return Agent(
        _normalize_model_name(model_name),
        instructions=system_prompt,
        toolsets=[mcp_server],
    )


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


def _register_mcp_lifecycle(app: Any, agent: Agent[None, str]) -> None:
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


def _build_app() -> tuple[Any, Agent[None, str] | None]:
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
                    "Installed pydantic-ai package does not support Agent.to_web() or Agent.to_ag_ui()."
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

    uvicorn.run("app.ai.scanner_chat_web:app", host=host, port=port, log_level=log_level)


if __name__ == "__main__":
    main()
