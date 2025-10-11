# -*- coding: utf-8 -*-
"""Timed control helper for three-way heating valves driven over MQTT."""
from __future__ import annotations

import asyncio
from typing import Optional

from backend.core.mqtt_client import mqtt_publish


class ThreeWayValve:
    """Time-based valve actuator able to move to arbitrary percentage positions."""

    def __init__(
        self,
        *,
        open_topic: str,
        close_topic: str,
        stop_topic: Optional[str] = None,
        open_payload: str = "ON",
        close_payload: str = "ON",
        stop_payload: str = "OFF",
        travel_time_s: float = 30.0,
        reverse_pause_s: float = 1.0,
        min_move_s: float = 0.5,
        ignore_delta_percent: float = 1.0,
    ) -> None:
        self.open_topic = open_topic
        self.close_topic = close_topic
        self.stop_topic = stop_topic
        self.open_payload = open_payload or "ON"
        self.close_payload = close_payload or "ON"
        self.stop_payload = stop_payload or "OFF"
        self.travel_time = max(0.0, float(travel_time_s or 0.0))
        self.reverse_pause_s = max(0.0, float(reverse_pause_s or 0.0))
        self.min_move_s = max(0.0, float(min_move_s or 0.0))
        self.ignore_delta_percent = max(0.0, float(ignore_delta_percent or 0.0))
        self.position: float = 0.0
        self._moving = False
        self._last_dir = 0  # -1 close, +1 open
        self._lock = asyncio.Lock()

    async def _publish(self, topic: Optional[str], payload: str) -> None:
        if topic:
            await mqtt_publish(topic, payload)

    async def stop(self) -> None:
        """Stop movement and ensure all topics are set to stop payload."""
        async with self._lock:
            await self._publish(self.open_topic, self.stop_payload)
            await self._publish(self.close_topic, self.stop_payload)
            if self.stop_topic:
                await self._publish(self.stop_topic, self.stop_payload)
            self._moving = False
            self._last_dir = 0

    async def move_to(self, target_percent: float) -> float:
        """Move valve to target percentage."""
        target = max(0.0, min(100.0, float(target_percent)))
        async with self._lock:
            if abs(target - self.position) < self.ignore_delta_percent:
                return self.position
            direction = 1 if target > self.position else -1
            if self._moving and self._last_dir != direction and self.reverse_pause_s > 0:
                await self._publish(self.open_topic, self.stop_payload)
                await self._publish(self.close_topic, self.stop_payload)
                if self.stop_topic:
                    await self._publish(self.stop_topic, self.stop_payload)
                await asyncio.sleep(self.reverse_pause_s)
            delta = abs(target - self.position) / 100.0
            move_time = self.travel_time * delta
            if move_time <= 0.0:
                move_time = 0.0
            if self.min_move_s > 0.0:
                move_time = max(move_time, self.min_move_s if delta > 0 else 0.0)
            stop_payload = self.stop_payload or "OFF"
            if direction > 0:
                await self._publish(self.close_topic, stop_payload)
                if self.stop_topic:
                    await self._publish(self.stop_topic, stop_payload)
                await self._publish(self.open_topic, self.open_payload)
            elif direction < 0:
                await self._publish(self.open_topic, stop_payload)
                if self.stop_topic:
                    await self._publish(self.stop_topic, stop_payload)
                await self._publish(self.close_topic, self.close_payload)
            else:
                return self.position
            self._moving = True
            self._last_dir = direction
            if move_time > 0.0:
                await asyncio.sleep(move_time)
            await self._publish(self.open_topic, stop_payload)
            await self._publish(self.close_topic, stop_payload)
            if self.stop_topic:
                await self._publish(self.stop_topic, stop_payload)
            self._moving = False
            self._last_dir = direction
            self.position = target
            return self.position
