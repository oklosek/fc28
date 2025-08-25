# -*- coding: utf-8 -*-
# backend/core/mqtt_client.py – MQTT (asyncio-mqtt)
import asyncio, json
from contextlib import AsyncExitStack
try:
    from asyncio_mqtt import Client, MqttError
except Exception:  # pragma: no cover - brak biblioteki w środowisku testowym
    Client = MqttError = None
from backend.core.config import settings, SENSORS, VENTS
from backend.core.models import SensorSnapshot
try:
    from backend.core.db import SessionLocal, SensorLog
    from sqlalchemy.orm import Session
except Exception:  # pragma: no cover - brak bazy w testach
    SessionLocal = None
    Session = None
    SensorLog = None

sensor_bus = SensorSnapshot()
sensor_bus.set_window({name: cfg.get("avg_window_s") for name, cfg in SENSORS.items()})

def set_avg_window(window: int):
    """Ustaw nowe okno uśredniania dla wszystkich czujników."""
    sensor_bus.set_window(window)

# Mapowanie tematów MQTT -> pola w sensor_bus
TOPIC_MAP = {cfg["topic"]: name for name, cfg in SENSORS.items()}

# Tematy dostępności wietrzników
VENT_AVAIL_TOPICS = [f'farmcare/vents/{v["id"]}/available' for v in VENTS]
# Tematy błędów krańcowych z urządzeń BONEIO
VENT_ERROR_TOPIC_MAP = {v["topics"].get("error_in"): v["id"] for v in VENTS if v["topics"].get("error_in")}

async def _handle_messages():
    if Client is None:
        return
    async with AsyncExitStack() as stack:
        client = Client(settings.MQTT_HOST, port=settings.MQTT_PORT,
                        username=settings.MQTT_USERNAME or None,
                        password=settings.MQTT_PASSWORD or None)
        await stack.enter_async_context(client)
        # Subskrypcje
        topics = list(TOPIC_MAP.keys()) + VENT_AVAIL_TOPICS + list(VENT_ERROR_TOPIC_MAP.keys())
        for t in topics:
            await client.subscribe(t)
        # Pętla odbioru
        async with client.unfiltered_messages() as messages:
            async for msg in messages:
                try:
                    payload = msg.payload.decode()
                    topic = msg.topic
                    if topic in TOPIC_MAP:
                        name = TOPIC_MAP[topic]
                        val = 1.0 if payload in ("true","True","1") else float(payload)
                        getattr(sensor_bus, name).add(val)
                        if SessionLocal and SensorLog:
                            # log do bazy (co przyjście), lekkie – można dodać filtr zmian
                            with SessionLocal() as s:  # type: Session
                                s.add(SensorLog(name=name, value=val))
                                s.commit()
                    elif topic in VENT_ERROR_TOPIC_MAP:
                        vid = VENT_ERROR_TOPIC_MAP[topic]
                        state = payload not in ("0", "false", "False", "OFF")
                        from backend.app import controller
                        if controller:
                            controller.mark_error(vid, state)
                    elif topic.startswith("farmcare/vents/") and topic.endswith("/available"):
                        # aktualizacja dostępności wietrznika – zapisze to kontroler (event)
                        pass
                except Exception as e:
                    print("MQTT parse error:", e)

async def mqtt_start():
    # uruchamiamy w tle
    asyncio.create_task(_handle_messages())

# Publikacje sterujące do BONEIO
async def mqtt_publish(topic: str, payload: str):
    if Client is None:
        return
    try:
        async with Client(settings.MQTT_HOST, port=settings.MQTT_PORT,
                          username=settings.MQTT_USERNAME or None,
                          password=settings.MQTT_PASSWORD or None) as c:
            await c.publish(topic, payload, qos=1)
    except MqttError as e:
        print("MQTT publish error:", e)
