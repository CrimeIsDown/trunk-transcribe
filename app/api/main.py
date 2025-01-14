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
from fastapi.responses import JSONResponse
import sentry_sdk

load_dotenv()

from app.api.routes import calls, config, health, sdrtrunk, talkgroups, tasks, websocket
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

    if (
        request.url.path not in ["/api/call-upload", "/healthz", "/ws"]
        and api_key
        and request.headers.get("Authorization", "") != f"Bearer {api_key}"
    ):
        return JSONResponse(content={"error": "Invalid key"}, status_code=401)
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
