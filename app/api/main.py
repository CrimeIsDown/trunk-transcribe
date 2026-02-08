#!/usr/bin/env python3

import logging
import os
import sys

from dotenv import load_dotenv
from fastapi import (
    FastAPI,
    Request,
    Response,
)
from fastapi.exception_handlers import request_validation_exception_handler
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
import sentry_sdk

load_dotenv()

from app.api.routes import (
    calls,
    config,
    health,
    sdrtrunk,
    talkgroups,
    tasks,
    websocket,
)
from app.utils.exceptions import before_send

sentry_dsn = os.getenv("SENTRY_DSN")
if sentry_dsn:
    sentry_sdk.init(
        dsn=sentry_dsn,
        release=os.getenv("GIT_COMMIT"),
        # Set traces_sample_rate to 1.0 to capture 100%
        # of transactions for performance monitoring.
        # We recommend adjusting this value in production.
        traces_sample_rate=float(os.getenv("SENTRY_TRACE_SAMPLE_RATE", "0.1")),
        _experiments={
            "profiles_sample_rate": float(
                os.getenv("SENTRY_PROFILE_SAMPLE_RATE", "0.1")
            ),
        },
        before_send=before_send,
    )

app = FastAPI()


def get_cors_allowed_origins() -> list[str]:
    configured_origins = os.getenv("CORS_ALLOWED_ORIGINS")
    if configured_origins:
        origins = [
            origin.strip()
            for origin in configured_origins.split(",")
            if origin.strip()
        ]
        if origins:
            return origins
    return [
        "http://localhost:3000",
        "http://localhost:3001",
    ]


def is_origin_allowed(origin: str | None) -> bool:
    if not origin:
        return False
    allowed_origins = get_cors_allowed_origins()
    return "*" in allowed_origins or origin in allowed_origins


app.add_middleware(
    CORSMiddleware,
    allow_origins=get_cors_allowed_origins(),
    allow_credentials=False,
    allow_methods=["*"],
    allow_headers=["Authorization", "Content-Type"],
)

logger = logging.getLogger()
logger.setLevel(os.getenv("UVICORN_LOG_LEVEL", "INFO").upper())
stream_handler = logging.StreamHandler(sys.stdout)
log_formatter = logging.Formatter(
    "%(asctime)s [%(processName)s: %(process)d] [%(threadName)s: %(thread)d] [%(levelname)s] %(name)s: %(message)s"
)
stream_handler.setFormatter(log_formatter)
logger.addHandler(stream_handler)


@app.middleware("http")
async def authenticate(request: Request, call_next) -> Response:
    api_key = os.getenv("API_KEY", "")

    if request.method == "OPTIONS":
        return await call_next(request)

    if (
        request.url.path not in ["/api/call-upload", "/healthz", "/ws"]
        and api_key
        and request.headers.get("Authorization", "") != f"Bearer {api_key}"
    ):
        response = JSONResponse(content={"error": "Invalid key"}, status_code=401)
        origin = request.headers.get("Origin")
        if is_origin_allowed(origin):
            response.headers["Access-Control-Allow-Origin"] = origin  # type: ignore
            response.headers["Vary"] = "Origin"
        return response
    return await call_next(request)


@app.exception_handler(RequestValidationError)
async def validation_exception_handler(
    request: Request, exc: RequestValidationError
) -> Response:
    if request.url.path == "/api/call-upload":
        try:
            field_name = exc.errors()[0]["loc"][1]
            return Response(f"Incomplete call data: no {field_name}", status_code=417)
        except Exception:
            pass
    return await request_validation_exception_handler(request, exc)


app.include_router(calls.router)
app.include_router(config.router)
app.include_router(health.router)
app.include_router(sdrtrunk.router)
app.include_router(talkgroups.router)
app.include_router(tasks.router)
app.include_router(websocket.router)
