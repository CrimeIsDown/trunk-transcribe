#!/usr/bin/env python3

import logging
import os
import sys

from fastapi import FastAPI, Request, Response
from fastapi.exception_handlers import request_validation_exception_handler
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
import sentry_sdk

from app.api.main import api_router
from app.core.config import settings
from app.utils.exceptions import before_send

if settings.SENTRY_DSN:
    sentry_sdk.init(
        dsn=settings.SENTRY_DSN,
        release=settings.GIT_COMMIT,
        traces_sample_rate=settings.SENTRY_TRACE_SAMPLE_RATE,
        _experiments={
            "profiles_sample_rate": settings.SENTRY_PROFILE_SAMPLE_RATE,
        },
        before_send=before_send,
    )

app = FastAPI(openapi_url=f"{settings.API_V1_STR}/openapi.json")


def get_cors_allowed_origins() -> list[str]:
    configured_origins = os.environ.get("CORS_ALLOWED_ORIGINS")
    if configured_origins is None:
        return settings.CORS_ALLOWED_ORIGINS
    return [origin.strip() for origin in configured_origins.split(",") if origin.strip()]


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
logger.setLevel(settings.UVICORN_LOG_LEVEL.upper())
stream_handler = logging.StreamHandler(sys.stdout)
log_formatter = logging.Formatter(
    "%(asctime)s [%(processName)s: %(process)d] [%(threadName)s: %(thread)d] [%(levelname)s] %(name)s: %(message)s"
)
stream_handler.setFormatter(log_formatter)
logger.addHandler(stream_handler)


@app.middleware("http")
async def authenticate(request: Request, call_next) -> Response:
    api_key = os.environ.get("API_KEY", settings.API_KEY)
    upload_path = f"{settings.API_V1_STR}/call-upload"
    websocket_path = f"{settings.API_V1_STR}/ws"
    health_path = f"{settings.API_V1_STR}/healthz"

    if request.method == "OPTIONS":
        return await call_next(request)

    if (
        request.url.path not in [upload_path, health_path, websocket_path]
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
    if request.url.path == f"{settings.API_V1_STR}/call-upload":
        try:
            field_name = exc.errors()[0]["loc"][1]
            return Response(f"Incomplete call data: no {field_name}", status_code=417)
        except Exception:
            pass
    return await request_validation_exception_handler(request, exc)


app.include_router(api_router, prefix=settings.API_V1_STR)
