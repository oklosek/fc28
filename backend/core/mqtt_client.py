# -*- coding: utf-8 -*-
# backend/core/mqtt_client.py – MQTT (asyncio-mqtt)
import asyncio, json
from contextlib import AsyncExitStack
from asyncio_mqtt import Client, MqttError
from backend.core.config import settings, SENSORS, VENTS
from backend.core.models import SensorSnapshot
from backend.core.db import SessionLocal, SensorLog
from sqlalchemy.orm import Session

sensor_bus = SensorSnapshot()

# Mapowanie tematów MQTT -> pola w sensor_bus
TOPIC_MAP = {
    SENSORS.get("internal_temp_topic", "farmcare/sensors/internalTemp"): ("internal_temp"),
    SENSORS.get("external_temp_topic", "farmcare/sensors/externalTemp"): ("external_temp"),
    SENSORS.get("internal_hum_topic",  "farmcare/sensors/internalHumidity"): ("internal_hum"),
    SENSORS.get("wind_speed_topic",    "farmcare/sensors/windSpeed"): ("wind_speed"),
    SENSORS.get("rain_topic",          "farmcare/sensors/rain"): ("rain"),
}

# Tematy dostępności/awarii wietrzników (każdy vent ma swój)
VENT_AVAIL_TOPICS = [f'farmcare/vents/{v["id"]}/available' for v in VENTS]

async def _handle_messages():
    async with AsyncExitStack() as stack:
        client = Client(settings.MQTT_HOST, port=settings.MQTT_PORT,
                        username=settings.MQTT_USERNAME or None,
                        password=settings.MQTT_PASSWORD or None)
        await stack.enter_async_context(client)
        # Subskrypcje
        topics = list(TOPIC_MAP.keys()) + VENT_AVAIL_TOPICS
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
                        # log do bazy (co przyjście), lekkie – można dodać filtr zmian
                        with SessionLocal() as s:  # type: Session
                            s.add(SensorLog(name=name, value=val))
                            s.commit()
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
    try:
        async with Client(settings.MQTT_HOST, port=settings.MQTT_PORT,
                          username=settings.MQTT_USERNAME or None,
                          password=settings.MQTT_PASSWORD or None) as c:
            await c.publish(topic, payload, qos=1)
    except MqttError as e:
        print("MQTT publish error:", e)
