import asyncio
from typing import Annotated
import os

from fastapi import (
    APIRouter,
    Depends,
    Query,
    WebSocket,
    WebSocketDisconnect,
    WebSocketException,
    status,
)
from sqlmodel import Session, select

from app.api.depends import get_db
from app.models import models


class ConnectionManager:
    def __init__(self):
        self.active_connections: list[WebSocket] = []

    async def connect(self, websocket: WebSocket):
        await websocket.accept()
        self.active_connections.append(websocket)

    def disconnect(self, websocket: WebSocket):
        self.active_connections.remove(websocket)

    async def send_personal_message(self, message: str, websocket: WebSocket):
        await websocket.send_text(message)

    async def broadcast(self, message: str):
        for connection in self.active_connections:
            await connection.send_text(message)


manager = ConnectionManager()


router = APIRouter()


async def get_api_key(
    websocket: WebSocket,
    api_key: Annotated[str | None, Query()] = None,
):
    if api_key != os.getenv("API_KEY", None):
        raise WebSocketException(code=status.WS_1008_POLICY_VIOLATION)
    return api_key


@router.websocket("/ws")
async def websocket_endpoint(
    websocket: WebSocket,
    db: Session = Depends(get_db),
    api_key: str = Depends(get_api_key),
):
    await manager.connect(websocket)

    last_id: int | None = None
    while not last_id:
        most_recent_calls = db.exec(
            select(models.Call.id, models.Call.transcript_plaintext)
            .order_by(models.Call.start_time.desc())  # type: ignore
            .limit(100)
        ).all()
        for call_tuple in most_recent_calls:
            if call_tuple[1]:  # transcript_plaintext
                last_id = call_tuple[0]  # id
                break
        if not last_id:
            await asyncio.sleep(1)

    try:
        while True:
            if last_id is not None:
                query = (
                    select(models.Call)
                    .where(models.Call.id > last_id)  # type: ignore
                    .where(
                        models.Call.transcript_plaintext != None  # noqa
                    )
                )
                calls = db.exec(query).all()

                if calls:
                    for call in calls:
                        await manager.broadcast(call.model_dump_json())
                    last_id = calls[-1].id

            await asyncio.sleep(1)
    except WebSocketDisconnect:
        manager.disconnect(websocket)
