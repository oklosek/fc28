# -*- coding: utf-8 -*-
# backend/routers/ws.py – WebSocket (push aktualizacji)
from fastapi import APIRouter, WebSocket, WebSocketDisconnect
from backend.core.mqtt_client import sensor_bus
import asyncio

router = APIRouter()

@router.websocket("/ws")
async def ws_endpoint(ws: WebSocket):
    from backend.app import controller

    await ws.accept()
    try:
        while True:
            payload = {
                "mode": controller.mode,
                "sensors": sensor_bus.averages(),
                "vents": {vid: v.position for vid, v in controller.vents.items()},
            }
            await ws.send_json(payload)
            await asyncio.sleep(1.0)
    except WebSocketDisconnect:
        return
