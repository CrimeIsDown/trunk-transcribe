from fastapi import APIRouter

from app.api.routes import (
    calls,
    config,
    health,
    sdrtrunk,
    talkgroups,
    tasks,
    websocket,
)

api_router = APIRouter()
api_router.include_router(calls.router)
api_router.include_router(config.router)
api_router.include_router(health.router)
api_router.include_router(sdrtrunk.router)
api_router.include_router(talkgroups.router)
api_router.include_router(tasks.router)
api_router.include_router(websocket.router)
