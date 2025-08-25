# -*- coding: utf-8 -*-
# backend/core/vents.py – klasa pojedynczego wietrznika sterowanego czasowo
import asyncio, time
from backend.core.mqtt_client import mqtt_publish

class Vent:
    """
    Sterowanie czasowe: otwarcie/zamknięcie przez odpowiedni czas odpowiadający procentowi.
    """
    def __init__(self, vid: int, name: str, travel_time_s: float,
                 boneio_device: str, up_topic: str, down_topic: str,
                 err_input_topic: str | None,
                 reverse_pause_s: float, min_move_s: float,
                 calibration_buffer_s: float, ignore_delta_percent: float):
        self.id = vid
        self.name = name
        self.travel_time = travel_time_s
        self.boneio_device = boneio_device
        self.up_topic = up_topic
        self.down_topic = down_topic
        self.err_input_topic = err_input_topic
        self.reverse_pause_s = reverse_pause_s
        self.min_move_s = min_move_s
        self.calibration_buffer_s = calibration_buffer_s
        self.ignore_delta_percent = ignore_delta_percent
        self.position = 0.0
        self.user_target = 0.0
        self.available = True
        self._moving = False
        self._last_dir = 0  # -1 close, +1 open

    async def stop(self):
        # BoneIO: oba przekaźniki OFF
        await mqtt_publish(self.up_topic, "OFF")
        await mqtt_publish(self.down_topic, "OFF")
        self._moving = False
        self._last_dir = 0

    async def move_to(self, target_percent: float):
        if not self.available: return
        target = max(0.0, min(100.0, float(target_percent)))
        if abs(target - self.position) < self.ignore_delta_percent:
            return
        # Kierunek
        direction = 1 if target > self.position else -1
        # Zmiana kierunku -> 1s pauzy
        if self._last_dir != 0 and self._last_dir != direction:
            await self.stop()
            await asyncio.sleep(self.reverse_pause_s)
        # Czas ruchu
        delta = abs(target - self.position) / 100.0
        move_time = max(self.min_move_s, delta * self.travel_time)
        # Publikacja MQTT
        if direction > 0:
            await mqtt_publish(self.down_topic, "OFF")
            await mqtt_publish(self.up_topic, "ON")
        else:
            await mqtt_publish(self.up_topic, "OFF")
            await mqtt_publish(self.down_topic, "ON")
        self._moving = True
        self._last_dir = direction
        await asyncio.sleep(move_time)
        # zatrzymaj i zaktualizuj pozycję
        await self.stop()
        self.position = target

    async def calibrate_close(self):
        """Domknięcie do 0% przez pełny travel_time."""
        if not self.available: return
        if self._last_dir == 1:
            await self.stop(); await asyncio.sleep(self.reverse_pause_s)
        await mqtt_publish(self.up_topic, "OFF")
        await mqtt_publish(self.down_topic, "ON")
        await asyncio.sleep(self.travel_time + self.calibration_buffer_s)
        await self.stop()
        self.position = 0.0
