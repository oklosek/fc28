# -*- coding: utf-8 -*-
# backend/core/controller.py – logika automatyczna, tryb ręczny, ograniczenia pogodowe, partie
import asyncio, threading, time, json
from collections import OrderedDict
from typing import Dict, List, Optional
from sqlalchemy.orm import Session
from backend.core.config import (
    VENTS,
    CONTROL,
    VENT_GROUPS,
    VENT_PLAN_STAGES,
    VENT_PLAN_CLOSE_STRATEGY,
    VENT_DEFAULTS,
)
from backend.core.db import SessionLocal, VentState, EventLog, RuntimeState, Setting
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
        self._groups: OrderedDict[str, dict] = OrderedDict()
        self._plan: List[dict] = []
        self._close_strategy = self._normalize_close_strategy(VENT_PLAN_CLOSE_STRATEGY)
        self._tolerance = float(CONTROL.get("ignore_delta_percent", 0.5)) or 0.5
        self._configure_plan(VENT_GROUPS, VENT_PLAN_STAGES, self._close_strategy)
        self._apply_plan_overrides()
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
                reverse_pause_s=v.get("reverse_pause_s", VENT_DEFAULTS.get("reverse_pause_s", 1.0)),
                min_move_s=v.get("min_move_s", VENT_DEFAULTS.get("min_move_s", 0.5)),
                calibration_buffer_s=v.get("calibration_buffer_s", VENT_DEFAULTS.get("calibration_buffer_s", 0.5)),
                ignore_delta_percent=v.get("ignore_delta_percent", VENT_DEFAULTS.get("ignore_delta_percent", 0.5)),
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

    def _normalize_close_strategy(self, value: Optional[str], default: str = "fifo") -> str:
        if value is None:
            return default
        if isinstance(value, (int, float)):
            return 'lifo' if int(value) == 1 else 'fifo'
        val = str(value).strip().lower()
        if val in ("fifo", "lifo"):
            return val
        if val in ("1", "true", "yes"):
            return 'lifo'
        if val in ("0", "false", "no"):
            return 'fifo'
        return default

    def _sanitize_step(self, value) -> float:
        try:
            step = float(value)
        except (TypeError, ValueError):
            step = float(CONTROL.get("step_percent", 10.0))
        if step <= 0:
            fallback = float(CONTROL.get("step_percent", 10.0)) or 1.0
            return fallback
        return step

    def _sanitize_delay(self, value) -> float:
        try:
            delay = float(value)
        except (TypeError, ValueError):
            delay = 0.0
        return delay if delay >= 0 else 0.0

    def export_groups(self) -> List[dict]:
        return [
            {"id": data["id"], "name": data["name"], "vents": list(data["vents"])}
            for data in self._groups.values()
        ]

    def export_plan(self) -> dict:
        return {
            "close_strategy": self._close_strategy,
            "close_strategy_flag": 1 if self._close_strategy == "lifo" else 0,
            "stages": [
                {
                    "id": stage["id"],
                    "name": stage["name"],
                    "mode": stage["mode"],
                    "step_percent": stage["step_percent"],
                    "delay_s": stage["delay_s"],
                    "close_strategy": stage["close_strategy"],
                    "close_strategy_flag": 1 if stage["close_strategy"] == "lifo" else 0,
                    "groups": list(stage["groups"]),
                }
                for stage in self._plan
            ],
        }

    def _configure_plan(
        self, group_cfg: List[dict], stage_cfg: List[dict], close_strategy: Optional[str] = None
    ) -> None:
        groups: "OrderedDict[str, dict]" = OrderedDict()
        for idx, grp in enumerate(group_cfg):
            gid = str(grp.get("id") or f"group_{idx + 1}")
            vents: List[int] = []
            for vid in grp.get("vents", []):
                try:
                    vid_int = int(vid)
                except (TypeError, ValueError):
                    continue
                if vid_int in self.vents:
                    vents.append(vid_int)
            groups[gid] = {
                "id": gid,
                "name": grp.get("name") or gid,
                "vents": vents,
            }
        self._groups = groups

        base_default = getattr(self, "_close_strategy", "fifo")
        default_close = self._normalize_close_strategy(close_strategy, base_default)
        self._close_strategy = default_close

        plan: List[dict] = []
        for idx, stage in enumerate(stage_cfg):
            raw_groups = stage.get("groups") or []
            stage_groups = [gid for gid in raw_groups if gid in groups]
            if not stage_groups:
                continue
            mode = "parallel" if str(stage.get("mode", "serial")).lower() == "parallel" else "serial"
            step = self._sanitize_step(stage.get("step_percent"))
            delay = self._sanitize_delay(stage.get("delay_s"))
            raw_stage_close = stage.get("close_strategy")
            if raw_stage_close is None:
                raw_stage_close = stage.get("close_strategy_flag")
            stage_close = self._normalize_close_strategy(raw_stage_close, default_close)
            plan.append(
                {
                    "id": stage.get("id") or f"stage_{idx + 1}",
                    "name": stage.get("name") or "",
                    "mode": mode,
                    "step_percent": step,
                    "delay_s": delay,
                    "close_strategy": stage_close,
                    "groups": stage_groups,
                }
            )
        self._plan = plan

    def _apply_plan_overrides(self) -> None:
        try:
            with SessionLocal() as session:
                stored_groups = session.get(Setting, "vent_groups")
                stored_plan = session.get(Setting, "vent_plan")
        except Exception:
            return

        groups_cfg: Optional[List[dict]] = None
        plan_cfg: Optional[dict] = None
        if stored_groups and stored_groups.value:
            try:
                data = json.loads(stored_groups.value)
                if isinstance(data, list):
                    groups_cfg = data
            except json.JSONDecodeError:
                pass
        if stored_plan and stored_plan.value:
            try:
                data = json.loads(stored_plan.value)
                if isinstance(data, dict):
                    plan_cfg = data
            except json.JSONDecodeError:
                pass

        if groups_cfg is None and plan_cfg is None:
            return

        base_plan = self.export_plan()
        base_groups = self.export_groups()
        final_groups = groups_cfg if groups_cfg is not None else base_groups
        stages_cfg = base_plan["stages"]
        close_strategy = base_plan["close_strategy"]
        if plan_cfg is not None:
            stages_cfg = plan_cfg.get("stages", stages_cfg)
            close_strategy = plan_cfg.get("close_strategy", close_strategy)
            if close_strategy is None:
                close_strategy = plan_cfg.get("close_strategy_flag", close_strategy)
        self._configure_plan(final_groups, stages_cfg, close_strategy)

    def _infer_closing(self, target_pct: float) -> bool:
        closers = sum(1 for v in self.vents.values() if v.position - target_pct > self._tolerance)
        openers = sum(1 for v in self.vents.values() if target_pct - v.position > self._tolerance)
        if closers > openers:
            return True
        if openers > closers:
            return False
        if self._last_auto_target is not None:
            return target_pct < self._last_auto_target
        return False

    async def _move_group_step(self, group_id: str, target_pct: float, step: float, closing: bool) -> bool:
        group = self._groups.get(group_id)
        if not group:
            return False
        tasks = []
        for vid in group["vents"]:
            vent = self.vents.get(vid)
            if not vent or not vent.available:
                continue
            if closing:
                if vent.position <= target_pct + self._tolerance:
                    continue
                next_pct = max(target_pct, vent.position - step)
                if vent.position - next_pct < self._tolerance:
                    continue
            else:
                if vent.position >= target_pct - self._tolerance:
                    continue
                next_pct = min(target_pct, vent.position + step)
                if next_pct - vent.position < self._tolerance:
                    continue
            tasks.append(vent.move_to(next_pct))
        if not tasks:
            return False
        await asyncio.gather(*tasks)
        return True

    async def _move_group_to_target(
        self, group_id: str, target_pct: float, step: float, closing: bool, step_delay: float
    ) -> None:
        while await self._move_group_step(group_id, target_pct, step, closing):
            if step_delay > 0:
                await asyncio.sleep(step_delay)

    async def _run_serial_stage(
        self,
        group_ids: List[str],
        target_pct: float,
        step: float,
        closing: bool,
        delay_between: float,
        step_delay: float,
    ) -> None:
        count = len(group_ids)
        for idx, gid in enumerate(group_ids):
            await self._move_group_to_target(gid, target_pct, step, closing, step_delay)
            if delay_between > 0 and idx < count - 1:
                await asyncio.sleep(delay_between)

    async def _run_parallel_stage(
        self,
        group_ids: List[str],
        target_pct: float,
        step: float,
        closing: bool,
        delay_between: float,
        step_delay: float,
    ) -> None:
        if not group_ids:
            return
        while True:
            moved_any = False
            for idx, gid in enumerate(group_ids):
                moved = await self._move_group_step(gid, target_pct, step, closing)
                if moved:
                    moved_any = True
                    if delay_between > 0 and idx < len(group_ids) - 1:
                        await asyncio.sleep(delay_between)
            if not moved_any:
                break
            if step_delay > 0:
                await asyncio.sleep(step_delay)

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
        diff_pct    = CONTROL.get("temp_diff_percent", 5.0)
        diff = s["internal_temp"] - target_temp
        # prosta proporcja: temp_diff_percent% / 1°C
        pct = 0.0
        if diff > 0 and s["external_temp"] < s["internal_temp"]:
            pct = min(100.0, diff * diff_pct)
        elif diff < 0 and s["external_temp"] > s["internal_temp"]:
            pct = min(100.0, abs(diff) * diff_pct)
        # wilgotność wymusza min. wietrzenie (gdy bez deszczu/wiatru krytycznego – sprawdzimy niżej)
        if s["internal_hum"] > hum_thr and pct < CONTROL.get("min_open_hum_percent", 20.0):
            pct = CONTROL.get("min_open_hum_percent", 20.0)
        return pct

    def _apply_safety(self, base_pct: float, s: dict, manual: bool) -> float:
        risk = CONTROL.get("wind_risk_ms", 10.0)
        crit = CONTROL.get("wind_crit_ms", 20.0)
        lim  = CONTROL.get("risk_open_limit_percent", 50.0)
        rain = s["rain"] > CONTROL.get("rain_threshold", 0.5)
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


    async def _move_in_batches(self, target_pct: float, closing: Optional[bool] = None) -> None:
        if closing is None:
            closing = self._infer_closing(target_pct)
        if not self._plan:
            await asyncio.gather(
                *[
                    self.vents[vid].move_to(target_pct)
                    for vid, vent in self.vents.items()
                    if vent.available
                ]
            )
            return
        step_delay = self._sanitize_delay(CONTROL.get("step_delay_s", 0.0))
        stage_sequence = (
            self._plan
            if not closing or self._close_strategy == "fifo"
            else list(reversed(self._plan))
        )
        for stage in stage_sequence:
            stage_close = stage.get("close_strategy", self._close_strategy)
            group_ids = list(stage.get("groups", []))
            if closing and stage_close == "lifo":
                group_ids = list(reversed(group_ids))
            if not group_ids:
                continue
            mode = stage.get("mode", "serial")
            step = self._sanitize_step(stage.get("step_percent"))
            delay = self._sanitize_delay(stage.get("delay_s"))
            if mode == "parallel":
                await self._run_parallel_stage(group_ids, target_pct, step, closing, delay, step_delay)
            else:
                await self._run_serial_stage(group_ids, target_pct, step, closing, delay, step_delay)

    async def _auto_move_to(self, target_pct: float, critical: bool) -> None:
        inferred_closing = self._infer_closing(target_pct)
        await self._move_in_batches(target_pct, closing=inferred_closing)

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
                s1 = sensor_bus.averages()
                s2 = self.rs485.averages()
                # merge ? je?li RS485 ma warto?? inn? ni? ``None`` to przyjmij j? jako bardziej wiarygodn?
                for k, v in s2.items():
                    if v is not None:
                        s1[k] = v
                required_keys = ("internal_temp", "external_temp", "internal_hum", "wind_speed")
                missing_required = any(s1.get(key) is None for key in required_keys)
                if s1.get("rain") is None:
                    s1["rain"] = 0.0
                if missing_required:
                    time.sleep(CONTROL.get("controller_loop_s", 1.0))
                    continue
                # tryb
                if self.mode == "auto":
                    base = self._compute_auto_target(s1)
                    target = self._apply_safety(base, s1, manual=False)
                    if self._last_auto_target is None or abs(target - self._last_auto_target) >= 1.0:
                        critical = s1["wind_speed"] >= CONTROL.get("wind_crit_ms", 20.0) or s1["rain"] > CONTROL.get("rain_threshold", 0.5)
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
                        if abs(safe - v.position) >= 1.0:
                            self._async_loop.run_until_complete(v.move_to(safe))
                            self._save_vent_state(vid)
                time.sleep(CONTROL.get("controller_loop_s", 1.0))
            except Exception as e:
                print("Controller loop error:", e)
                time.sleep(CONTROL.get("controller_loop_s", 1.0))

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

    def manual_set_group(self, group_id: str, pct: float) -> bool:
        self.set_mode("manual")
        group = self._groups.get(group_id)
        if not group:
            return False

        async def _move():
            tasks = []
            for vid in group["vents"]:
                vent = self.vents.get(vid)
                if vent and vent.available:
                    tasks.append(vent.move_to(pct))
            if tasks:
                await asyncio.gather(*tasks)
            for vid in group["vents"]:
                vent = self.vents.get(vid)
                if vent and vent.available:
                    vent.user_target = pct
                    self._save_vent_state(vent.id)

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

    def update_config(
        self,
        control: Optional[dict] = None,
        vent_groups: Optional[List[dict]] = None,
        vent_plan: Optional[dict] = None,
    ) -> None:
        if control:
            CONTROL.update(control)
        if vent_groups is not None or vent_plan is not None:
            groups_cfg = vent_groups if vent_groups is not None else self.export_groups()
            plan_cfg = vent_plan if isinstance(vent_plan, dict) else self.export_plan()
            stages_cfg = plan_cfg.get("stages", [])
            close_strategy = plan_cfg.get("close_strategy")
            if close_strategy is None:
                close_strategy = plan_cfg.get("close_strategy_flag")
            self._configure_plan(groups_cfg, stages_cfg, close_strategy)




