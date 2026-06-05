import asyncio
import json

from fastapi import APIRouter, WebSocket, WebSocketDisconnect

router = APIRouter(tags=["live"])


@router.websocket("/ws/live")
async def live_updates(websocket: WebSocket) -> None:
    await websocket.accept()
    try:
        while True:
            await websocket.send_text(json.dumps({"type": "heartbeat", "status": "ok"}))
            await asyncio.sleep(5)
    except WebSocketDisconnect:
        return

