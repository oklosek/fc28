# -*- coding: utf-8 -*-
# backend/routers/ws.py – WebSocket (push aktualizacji)
from fastapi import APIRouter, WebSocket, WebSocketDisconnect
from backend.core.mqtt_client import sensor_bus
from backend.app import controller
import asyncio

router = APIRouter()

@router.websocket("/ws")
async def ws_endpoint(ws: WebSocket):
    await ws.accept()
    try:
        while True:
            payload = {
                "mode": controller.mode,
                "sensors": {
                    "internal_temp": sensor_bus.internal_temp.avg(),
                    "external_temp": sensor_bus.external_temp.avg(),
                    "internal_hum":  sensor_bus.internal_hum.avg(),
                    "wind_speed":    sensor_bus.wind_speed.avg(),
                    "rain":          sensor_bus.rain.avg(),
                },
                "vents": { vid: v.position for vid, v in controller.vents.items() }
            }
            await ws.send_json(payload)
            await asyncio.sleep(1.0)
    except WebSocketDisconnect:
        return
