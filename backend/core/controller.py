# -*- coding: utf-8 -*-
# backend/core/controller.py – logika automatyczna, tryb ręczny, ograniczenia pogodowe, partie
import asyncio, threading, time
from typing import Dict, List
from sqlalchemy.orm import Session
from backend.core.config import VENTS, CONTROL, VENT_GROUPS
from backend.core.db import SessionLocal, VentState, EventLog, RuntimeState
from backend.core.mqtt_client import sensor_bus
from backend.core.rs485 import RS485Manager
from backend.core.vents import Vent

class Controller:
    def __init__(self, rs485_manager: RS485Manager):
        self.rs485 = rs485_manager
        self.mode = "auto"  # 'auto' | 'manual'
        self.vents: Dict[int, Vent] = {}
        self._running = False
        self._thread = None
        self._async_loop = None
        self._load_vents_from_config()
        self._load_state_from_db()
        self._batch_cfg = VENT_GROUPS  # sekwencje/partie otwierania
        self._last_auto_target = None

    def _load_vents_from_config(self):
        for v in VENTS:
            vent = Vent(
                vid=v["id"],
                name=v["name"],
                travel_time_s=v["travel_time_s"],
                boneio_device=v["boneio_device"],
                up_topic=v["topics"]["up"],
                down_topic=v["topics"]["down"],
                err_input_topic=v["topics"].get("error_in"),
            )
            self.vents[vent.id] = vent

    def _load_state_from_db(self):
        with SessionLocal() as s:
            # runtime mode
            kv = s.get(RuntimeState, "mode")
            if kv: self.mode = kv.value
            # vent states
            for v in self.vents.values():
                vs = s.get(VentState, v.id)
                if vs:
                    v.position = float(vs.position)
                    v.available = bool(vs.available)
                    v.user_target = float(vs.user_target)
                else:
                    s.add(VentState(id=v.id, name=v.name, position=0.0, available=True, user_target=0.0))
            s.commit()

    def start(self):
        self._running = True
        self._thread = threading.Thread(target=self._loop, daemon=True)
        self._thread.start()

    def stop(self):
        self._running = False

    def set_mode(self, mode: str):
        if mode not in ("auto","manual"): return
        prev = self.mode
        self.mode = mode
        with SessionLocal() as s:
            s.merge(RuntimeState(key="mode", value=self.mode)); s.commit()
            s.add(EventLog(level="INFO", event="MODE_CHANGE", meta={"mode": self.mode})); s.commit()
        if prev != mode:
            if mode == "manual":
                # zatrzymaj wszystkie ruchy
                async def _stop_all():
                    await asyncio.gather(*[v.stop() for v in self.vents.values()])
                if self._async_loop:
                    asyncio.run_coroutine_threadsafe(_stop_all(), self._async_loop)
            else:
                self._last_auto_target = None
                self.calibrate_all()

    def _compute_auto_target(self, s: dict) -> float:
        target_temp = CONTROL.get("target_temp_c", 25.0)
        hum_thr     = CONTROL.get("humidity_thr", 70.0)
        diff = s["internal_temp"] - target_temp
        # prosta proporcja: 5% / 1°C
        pct = 0.0
        if diff > 0 and s["external_temp"] < s["internal_temp"]:
            pct = min(100.0, diff * 5.0)
        elif diff < 0 and s["external_temp"] > s["internal_temp"]:
            pct = min(100.0, abs(diff) * 5.0)
        # wilgotność wymusza min. wietrzenie (gdy bez deszczu/wiatru krytycznego – sprawdzimy niżej)
        if s["internal_hum"] > hum_thr and pct < CONTROL.get("min_open_hum_percent", 20.0):
            pct = CONTROL.get("min_open_hum_percent", 20.0)
        return pct

    def _apply_safety(self, base_pct: float, s: dict, manual: bool) -> float:
        risk = CONTROL.get("wind_risk_ms", 10.0)
        crit = CONTROL.get("wind_crit_ms", 20.0)
        lim  = CONTROL.get("risk_open_limit_percent", 50.0)
        rain = s["rain"] > CONTROL.get("rain_thr", 0.5)
        allow_override = CONTROL.get("allow_humidity_override", False)
        # krytyk: domyślnie zamknij wszystko; opcjonalna szczelina przy wilgotności
        if s["wind_speed"] >= crit or rain:
            if allow_override and s["internal_hum"] > CONTROL.get("humidity_thr", 70.0):
                return CONTROL.get("crit_hum_crack_percent", 10.0)
            return 0.0
        # ryzykowny wiatr: ogranicz max
        if s["wind_speed"] >= risk and base_pct > lim:
            return lim
        return base_pct

    async def _move_in_batches(self, target_pct: float):
        """Otwieranie partiami wg VENT_GROUPS: np. najpierw 6 dachowych, potem boczne itd."""
        delay_default = CONTROL.get("group_delay_s", 5)
        if not self._batch_cfg:
            await asyncio.gather(*[self.vents[v].move_to(target_pct) for v in self.vents])
            return
        for group in self._batch_cfg:
            ids: List[int] = group["vents"]
            delay_s = group.get("delay_s", delay_default)
            await asyncio.gather(*[self.vents[vid].move_to(target_pct) for vid in ids if vid in self.vents])
            if delay_s > 0:
                await asyncio.sleep(delay_s)

    async def _auto_move_to(self, target_pct: float, critical: bool):
        if critical:
            await self._move_in_batches(target_pct)
            return
        step = CONTROL.get("step_percent", 10.0)
        delay = CONTROL.get("step_delay_s", 10.0)
        tolerance = CONTROL.get("movement_tolerance_percent", 0.5)
        start = self._last_auto_target
        if start is None:
            if self.vents:
                start = sum(v.position for v in self.vents.values()) / len(self.vents)
            else:
                start = 0.0
        current = start
        if target_pct > current:
            while current < target_pct - tolerance:
                current = min(current + step, target_pct)
                await self._move_in_batches(current)
                if current != target_pct:
                    await asyncio.sleep(delay)
        else:
            while current > target_pct + tolerance:
                current = max(current - step, target_pct)
                await self._move_in_batches(current)
                if current != target_pct:
                    await asyncio.sleep(delay)

    def _save_vent_state(self, vid: int):
        v = self.vents[vid]
        with SessionLocal() as s:
            row = s.get(VentState, vid); 
            if row:
                row.position = float(v.position)
                row.available = bool(v.available)
                row.user_target = float(v.user_target)
            s.commit()

    def _loop(self):
        self._async_loop = asyncio.new_event_loop()
        asyncio.set_event_loop(self._async_loop)
        while self._running:
            try:
                # zbierz średnie: z MQTT i RS485 (łączymy – preferuj RS485 jeśli skonfigurowany)
                s1 = {
                    "internal_temp": sensor_bus.internal_temp.avg(),
                    "external_temp": sensor_bus.external_temp.avg(),
                    "internal_hum":  sensor_bus.internal_hum.avg(),
                    "wind_speed":    sensor_bus.wind_speed.avg(),
                    "rain":          sensor_bus.rain.avg(),
                }
                s2 = self.rs485.averages()
                # merge – jeśli RS485 wartość != 0 to przyjmij RS485 jako bardziej wiarygodny
                for k in s1:
                    if s2.get(k, 0) > 0: s1[k] = s2[k]
                # tryb
                if self.mode == "auto":
                    base = self._compute_auto_target(s1)
                    target = self._apply_safety(base, s1, manual=False)
                    if (
                        self._last_auto_target is None
                        or abs(target - self._last_auto_target)
                        >= CONTROL.get("target_change_percent", 1.0)
                    ):
                        critical = (
                            s1["wind_speed"] >= CONTROL.get("wind_crit_ms", 20.0)
                            or s1["rain"] > CONTROL.get("rain_thr", 0.5)
                        )
                        self._async_loop.run_until_complete(self._auto_move_to(target, critical))
                        for vid in self.vents:
                            self.vents[vid].user_target = target
                            self._save_vent_state(vid)
                        self._last_auto_target = target
                else:
                    # manual – tylko bezpieczeństwo
                    for vid, v in self.vents.items():
                        desired = v.user_target
                        safe = self._apply_safety(desired, s1, manual=True)
                        if abs(safe - v.position) >= CONTROL.get("target_change_percent", 1.0):
                            self._async_loop.run_until_complete(v.move_to(safe))
                            self._save_vent_state(vid)
                time.sleep(1.0)
            except Exception as e:
                print("Controller loop error:", e)
                time.sleep(1.0)

    # API akcji
    def manual_set_all(self, pct: float):
        self.set_mode("manual")
        async def _move():
            await self._move_in_batches(pct)
            for v in self.vents.values():
                if v.available:
                    v.user_target = pct
                    self._save_vent_state(v.id)
        if self._async_loop:
            asyncio.run_coroutine_threadsafe(_move(), self._async_loop)
        return True

    def manual_set_one(self, vent_id: int, pct: float):
        self.set_mode("manual")
        if vent_id in self.vents:
            v = self.vents[vent_id]
            if v.available: v.user_target = pct
            return True
        return False

    def mark_error(self, vent_id: int, state: bool):
        if vent_id in self.vents:
            self.vents[vent_id].available = not state  # error=true => available=false
            self._save_vent_state(vent_id)

    def calibrate_all(self):
        async def _cal():
            for v in self.vents.values():
                if v.available:
                    await v.calibrate_close()
                    self._save_vent_state(v.id)
        if self._async_loop:
            asyncio.run_coroutine_threadsafe(_cal(), self._async_loop)

    def update_config(self, control: dict | None = None, vent_groups: List[dict] | None = None):
        if control:
            CONTROL.update(control)
        if vent_groups is not None:
            self._batch_cfg = vent_groups
