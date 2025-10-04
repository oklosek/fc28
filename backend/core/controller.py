# -*- coding: utf-8 -*-
# backend/core/controller.py Ä‚ËĂ˘â€šÂ¬Ă˘â‚¬Ĺ› logika automatyczna, tryb rÄ‚â€žĂ˘â€žËczny, ograniczenia pogodowe, partie
import asyncio, threading, time, json
from datetime import datetime, time as dt_time
from collections import OrderedDict
from typing import Dict, List, Optional
from sqlalchemy.orm import Session
from backend.core.config import (
    VENTS,
    CONTROL,
    HEATING,
    VENT_GROUPS,
    VENT_PLAN_STAGES,
    VENT_PLAN_CLOSE_STRATEGY,
    VENT_DEFAULTS,
    EXTERNAL_CONNECTION,
    BONEIOS,
)
from backend.core.db import SessionLocal, VentState, RuntimeState, Setting, EventLog
from backend.core.mqtt_client import sensor_bus, mqtt_publish
from backend.core.rs485 import RS485Manager
from backend.core import test_mode
from backend.core.vents import Vent
from backend.core.notifications import log_event

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
        self._vent_to_groups: Dict[int, List[str]] = {}
        self._last_env: dict = {}
        self._last_env_snapshot: dict = {"sensors": {}, "sources": {}}
        self._heating_state: Optional[bool] = None
        self._co2_alert_active: bool = False
        self._heating_day_start: Optional[dt_time] = None
        self._heating_night_start: Optional[dt_time] = None
        self._thermal_day_start: Optional[dt_time] = None
        self._thermal_night_start: Optional[dt_time] = None
        self._night_max_open: float = 40.0
        self._close_strategy = self._normalize_close_strategy(VENT_PLAN_CLOSE_STRATEGY)
        self._apply_control_overrides()
        self._apply_heating_overrides()
        self._tolerance = float(CONTROL.get("ignore_delta_percent", 0.5)) or 0.5
        self._configure_plan(VENT_GROUPS, VENT_PLAN_STAGES, self._close_strategy)
        self._apply_plan_overrides()
        self._refresh_schedules()
        self._last_auto_target = None
        self._manual_lock = None

    def _load_vents_from_config(self, vent_specs: Optional[List[dict]] = None):
        self.vents.clear()
        data = vent_specs if vent_specs is not None else VENTS
        for v in data:
            vent = Vent(
                vid=v["id"],
                name=v["name"],
                travel_time_s=v["travel_time_s"],
                boneio_device=v.get("boneio_device", "boneio_main"),
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
            if kv:
                stored_mode = str(kv.value).strip().lower()
                if stored_mode == "auto":
                    self.mode = "auto"
                else:
                    # Tryb ręczny nie powinien być stanem startowym – po restarcie
                    # zawsze wracamy do trybu automatycznego i aktualizujemy wpis.
                    self.mode = "auto"
                    kv.value = "auto"
            # vent states
            for v in self.vents.values():
                vs = s.get(VentState, v.id)
                if vs:
                    position = vs.position
                    try:
                        v.position = float(position) if position is not None else 0.0
                    except (TypeError, ValueError):
                        v.position = 0.0

                    available = vs.available
                    if available is None:
                        v.available = True
                    else:
                        v.available = bool(available)

                    user_target = vs.user_target
                    try:
                        v.user_target = float(user_target) if user_target is not None else 0.0
                    except (TypeError, ValueError):
                        v.user_target = 0.0
                else:
                    s.add(
                        VentState(
                            id=v.id,
                            name=v.name,
                            position=0.0,
                            available=True,
                            user_target=0.0,
                        )
                    )
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

    def _clamp_percent(self, value, default: Optional[float] = None) -> Optional[float]:
        if value is None:
            return default
        try:
            pct = float(value)
        except (TypeError, ValueError):
            return default
        if pct < 0.0:
            return 0.0
        if pct > 100.0:
            return 100.0
        return pct

    def _normalize_wind_ranges(self, raw) -> List[List[float]]:
        if raw is None:
            return []
        items = raw
        if isinstance(items, dict):
            items = [items]
        if not isinstance(items, (list, tuple)):
            return []
        ranges: List[List[float]] = []
        for entry in items:
            if isinstance(entry, dict):
                start = entry.get("start", entry.get("from"))
                end = entry.get("end", entry.get("to"))
            elif isinstance(entry, (list, tuple)) and len(entry) >= 2:
                start, end = entry[0], entry[1]
            else:
                continue
            try:
                start_val = float(start) % 360.0
                end_val = float(end) % 360.0
            except (TypeError, ValueError):
                continue
            ranges.append([start_val, end_val])
        return ranges

    def _direction_in_range(self, direction: float, start: float, end: float) -> bool:
        if start == end:
            return True
        if start <= end:
            return start <= direction <= end
        return direction >= start or direction <= end

    def export_groups(self) -> List[dict]:
        groups: List[dict] = []
        for data in self._groups.values():
            item = {
                "id": data["id"],
                "name": data["name"],
                "vents": list(data["vents"]),
            }
            item["wind_upwind_deg"] = [list(rng) for rng in data.get("wind_upwind_deg", [])]
            item["wind_lock_enabled"] = bool(data.get("wind_lock_enabled", True))
            item["wind_lock_close_percent"] = data.get("wind_lock_close_percent")
            groups.append(item)
        return groups

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

    def export_environment_snapshot(self) -> dict:
        return {
            "sensors": dict(self._last_env_snapshot.get("sensors", {})),
            "sources": dict(self._last_env_snapshot.get("sources", {})),
        }

    def export_rs485_status(self) -> List[dict]:
        return self.rs485.status()

    def export_heating(self) -> Optional[dict]:
        if not isinstance(HEATING, dict):
            return None
        def _float_or_none(value):
            if value is None:
                return None
            try:
                return float(value)
            except (TypeError, ValueError):
                return None
        data = {
            "enabled": bool(HEATING.get("enabled")),
            "topic": HEATING.get("topic"),
            "payload_on": HEATING.get("payload_on"),
            "payload_off": HEATING.get("payload_off"),
            "day_target_c": _float_or_none(HEATING.get("day_target_c")),
            "night_target_c": _float_or_none(HEATING.get("night_target_c")),
            "hysteresis_c": _float_or_none(HEATING.get("hysteresis_c")),
            "day_start": HEATING.get("day_start"),
            "night_start": HEATING.get("night_start"),
        }
        return data

    def _configure_plan(
        self, group_cfg: List[dict], stage_cfg: List[dict], close_strategy: Optional[str] = None
    ) -> None:
        groups: "OrderedDict[str, dict]" = OrderedDict()
        vent_to_groups: Dict[int, List[str]] = {}
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
            wind_raw = grp.get("wind_upwind_deg")
            if wind_raw is None:
                wind_raw = grp.get("wind_upwind")
            ranges = self._normalize_wind_ranges(wind_raw)
            wind_lock_enabled = bool(grp.get("wind_lock_enabled", True))
            close_pct = self._clamp_percent(grp.get("wind_lock_close_percent"), None)
            if close_pct is None and ranges:
                close_pct = 0.0
            group_data = {
                "id": gid,
                "name": grp.get("name") or gid,
                "vents": vents,
                "wind_upwind_deg": ranges,
                "_wind_ranges": [(rng[0], rng[1]) for rng in ranges],
                "wind_lock_enabled": wind_lock_enabled,
                "wind_lock_close_percent": close_pct,
                "target_override": None,
                "force_close": False,
                "wind_locked": False,
                "wind_last_state": None,
            }
            groups[gid] = group_data
            for vid in vents:
                vent_to_groups.setdefault(vid, []).append(gid)
        self._groups = groups
        self._vent_to_groups = vent_to_groups

        base_default = getattr(self, "_close_strategy", "fifo")
        default_close = self._normalize_close_strategy(close_strategy, base_default)
        self._close_strategy = default_close

        plan: List[dict] = []
        valid_groups = set(groups.keys())
        for idx, stage in enumerate(stage_cfg or []):
            raw_groups = stage.get("groups") or []
            stage_groups = [gid for gid in raw_groups if gid in valid_groups]
            if not stage_groups:
                continue
            mode = "parallel" if str(stage.get("mode", "serial")).strip().lower() == "parallel" else "serial"
            step = self._sanitize_step(stage.get("step_percent"))
            delay = self._sanitize_delay(stage.get("delay_s"))
            raw_stage_close = stage.get("close_strategy")
            if raw_stage_close is None:
                raw_stage_close = stage.get("close_strategy_flag")
            stage_close = self._normalize_close_strategy(raw_stage_close, default_close)
            plan.append({
                "id": stage.get("id") or f"stage_{idx + 1}",
                "name": stage.get("name") or "",
                "mode": mode,
                "step_percent": step,
                "delay_s": delay,
                "close_strategy": stage_close,
                "groups": stage_groups,
            })
        self._plan = plan

    def _log_event(self, event: str, *, level: str = "INFO", meta: Optional[dict] = None, category: Optional[str] = None) -> None:
        payload = dict(meta or {})
        if category:
            payload.setdefault("category", category)
        try:
            with SessionLocal() as session:
                session.add(EventLog(level=level, event=event, meta=payload or None))
                session.commit()
        except Exception:
            log_event(event, level=level, meta=meta, category=category)

    def _log_wind_event(self, group_id: str, locked: bool, direction: Optional[float]) -> None:
        self._log_event(
            "WIND_LOCK_ON" if locked else "WIND_LOCK_OFF",
            meta={"group": group_id, "wind_direction": direction},
            category="wind",
        )

    def _update_group_wind_state(self, sensors: dict) -> None:
        wind_raw = sensors.get("wind_direction")
        try:
            wind_dir = None if wind_raw is None else float(wind_raw) % 360.0
        except (TypeError, ValueError):
            wind_dir = None
        global_enabled = bool(CONTROL.get("wind_lock_enabled", True))
        for gid, group in self._groups.items():
            ranges = group.get("_wind_ranges") or []
            use_lock = bool(ranges) and global_enabled and group.get("wind_lock_enabled", True)
            locked = False
            if use_lock and wind_dir is not None:
                for start, end in ranges:
                    if self._direction_in_range(wind_dir, start, end):
                        locked = True
                        break
            override = None
            force_close = False
            if locked and use_lock:
                close_pct = group.get("wind_lock_close_percent")
                if close_pct is None:
                    close_pct = 0.0
                override = close_pct
                force_close = True
            group["wind_locked"] = locked
            group["target_override"] = override
            group["force_close"] = force_close
            prev_state = group.get("wind_last_state")
            if prev_state is None:
                group["wind_last_state"] = locked
                if use_lock and wind_dir is not None:
                    self._log_wind_event(gid, locked, wind_dir)
            elif prev_state != locked:
                group["wind_last_state"] = locked
                if use_lock and wind_dir is not None:
                    self._log_wind_event(gid, locked, wind_dir)

    def _refresh_control_schedule(self) -> None:
        self._thermal_day_start = self._parse_time_of_day(CONTROL.get("day_start"))
        self._thermal_night_start = self._parse_time_of_day(CONTROL.get("night_start"))
        cap = self._clamp_percent(CONTROL.get("night_max_open_percent"), None)
        if cap is None:
            cap = 40.0
        self._night_max_open = cap

    def _refresh_heating_schedule(self) -> None:
        if isinstance(HEATING, dict):
            self._heating_day_start = self._parse_time_of_day(HEATING.get("day_start"))
            self._heating_night_start = self._parse_time_of_day(HEATING.get("night_start"))
        else:
            self._heating_day_start = None
            self._heating_night_start = None

    def _refresh_schedules(self) -> None:
        self._refresh_control_schedule()
        self._refresh_heating_schedule()

    def _sanitize_heating_config(self, payload: Dict[str, object]) -> Dict[str, object]:
        if not isinstance(payload, dict):
            return {}
        sanitized: Dict[str, object] = {}
        if "enabled" in payload:
            sanitized["enabled"] = bool(payload.get("enabled"))
        if "topic" in payload:
            topic = payload.get("topic")
            if topic is None:
                sanitized["topic"] = None
            else:
                text = str(topic).strip()
                sanitized["topic"] = text or None
        for key in ("payload_on", "payload_off"):
            if key in payload:
                value = payload.get(key)
                if value is None:
                    sanitized[key] = None
                else:
                    sanitized[key] = str(value)
        for key in ("day_target_c", "night_target_c", "hysteresis_c"):
            if key in payload:
                value = payload.get(key)
                if value is None:
                    sanitized[key] = None
                else:
                    try:
                        sanitized[key] = float(value)
                    except (TypeError, ValueError):
                        continue
        for key in ("day_start", "night_start"):
            if key in payload:
                value = payload.get(key)
                if value is None:
                    sanitized[key] = None
                else:
                    sanitized[key] = str(value).strip() or None
        return sanitized

    def _is_daytime(self, now: datetime, day_start: Optional[dt_time], night_start: Optional[dt_time]) -> bool:
        if not day_start or not night_start:
            return True
        if day_start == night_start:
            return True
        current = now.time()
        if day_start < night_start:
            return day_start <= current < night_start
        return current >= day_start or current < night_start

    def _is_nighttime(self, now: datetime) -> bool:
        return not self._is_daytime(now, self._thermal_day_start, self._thermal_night_start)

    def _resolve_environment_target(self, now: datetime) -> float:
        base = CONTROL.get("target_temp_c", 25.0)
        try:
            base_val = float(base)
        except (TypeError, ValueError):
            base_val = 25.0
        day_raw = CONTROL.get("day_target_temp_c")
        night_raw = CONTROL.get("night_target_temp_c")
        try:
            day_val = float(day_raw) if day_raw is not None else base_val
        except (TypeError, ValueError):
            day_val = base_val
        try:
            night_val = float(night_raw) if night_raw is not None else base_val
        except (TypeError, ValueError):
            night_val = base_val
        if self._is_daytime(now, self._thermal_day_start, self._thermal_night_start):
            return day_val
        return night_val

    def _is_heating_enabled(self) -> bool:
        return isinstance(HEATING, dict) and bool(HEATING.get("enabled"))

    def _update_co2_alert(self, co2_value: Optional[float], threshold: Optional[float]) -> None:
        active = bool(threshold is not None and co2_value is not None and co2_value > threshold)
        if active == self._co2_alert_active:
            return
        self._co2_alert_active = active
        event = "CO2_HIGH" if active else "CO2_NORMAL"
        level = "WARN" if active else "INFO"
        meta = {"value": co2_value, "threshold": threshold}
        self._log_event(event, level=level, meta=meta, category="environment")

    def _parse_time_of_day(self, value) -> Optional[dt_time]:
        if value is None:
            return None
        if isinstance(value, dt_time):
            return value
        if isinstance(value, str):
            try:
                hour_str, minute_str = value.strip().split(":", 1)
                hour = int(hour_str)
                minute = int(minute_str)
            except ValueError:
                return None
            hour = max(0, min(23, hour))
            minute = max(0, min(59, minute))
            return dt_time(hour=hour, minute=minute)
        return None

    def _resolve_heating_target(self, now: datetime) -> Optional[float]:
        if not isinstance(HEATING, dict):
            return None
        day_target = HEATING.get("day_target_c")
        night_target = HEATING.get("night_target_c")
        try:
            day_val = float(day_target) if day_target is not None else None
        except (TypeError, ValueError):
            day_val = None
        try:
            night_val = float(night_target) if night_target is not None else None
        except (TypeError, ValueError):
            night_val = None
        if day_val is None and night_val is None:
            return None
        if day_val is None:
            return night_val
        if night_val is None:
            return day_val
        day_start = self._heating_day_start or self._thermal_day_start
        night_start = self._heating_night_start or self._thermal_night_start
        if not day_start or not night_start:
            return day_val
        if self._is_daytime(now, day_start, night_start):
            return day_val
        return night_val

    def _handle_heating(self, sensors: dict) -> None:
        if not isinstance(HEATING, dict):
            self._heating_state = None
            return
        if not self._is_heating_enabled():
            if self._heating_state:
                topic = HEATING.get("topic")
                if topic:
                    self._set_heating(False, topic)
                else:
                    self._heating_state = None
            else:
                self._heating_state = None
            return
        topic = HEATING.get("topic")
        if not topic:
            return
        try:
            internal_temp = float(sensors.get("internal_temp"))
        except (TypeError, ValueError):
            return
        target = self._resolve_heating_target(datetime.now())
        if target is None:
            return
        hysteresis = HEATING.get("hysteresis_c", 5.0)
        try:
            hysteresis = float(hysteresis)
        except (TypeError, ValueError):
            hysteresis = 5.0
        if hysteresis < 0.0:
            hysteresis = 0.0
        on_threshold = target - hysteresis
        current_state = self._heating_state
        desired_state = current_state
        if current_state is None:
            desired_state = internal_temp <= on_threshold
        elif current_state:
            if internal_temp >= target:
                desired_state = False
        else:
            if internal_temp <= on_threshold:
                desired_state = True
        if desired_state is None:
            desired_state = False
        if desired_state != current_state:
            self._set_heating(desired_state, topic)

    def _set_heating(self, state: bool, topic: str) -> None:
        payload_key = "payload_on" if state else "payload_off"
        payload = HEATING.get(payload_key) or ("ON" if state else "OFF")
        success = True
        if topic and self._async_loop:
            try:
                self._async_loop.run_until_complete(mqtt_publish(topic, payload))
            except Exception as exc:
                print("Heating publish error:", exc)
                success = False
        if success:
            self._heating_state = state
            try:
                with SessionLocal() as session:
                    session.add(EventLog(
                        level="INFO",
                        event="HEATING_ON" if state else "HEATING_OFF",
                        meta={"topic": topic, "payload": payload},
                    ))
                    session.commit()
            except Exception:
                pass

    def _coerce_control_value(self, key: str, raw: object):
        baseline = CONTROL.get(key)
        value = raw
        if isinstance(value, str):
            stripped = value.strip()
            if stripped == "":
                return baseline
            value = stripped
        if isinstance(baseline, bool):
            if isinstance(value, str):
                lowered = value.lower()
                return lowered in {"1", "true", "yes", "on"}
            return bool(value)
        if isinstance(baseline, int) and not isinstance(baseline, bool):
            try:
                return int(float(value))
            except (TypeError, ValueError):
                return baseline
        if isinstance(baseline, float):
            try:
                return float(value)
            except (TypeError, ValueError):
                return baseline
        if isinstance(value, str):
            lowered = value.lower()
            if lowered in {"1", "true", "yes", "on"}:
                return True
            if lowered in {"0", "false", "no", "off"}:
                return False
            try:
                if "." in value:
                    return float(value)
                return int(value)
            except ValueError:
                pass
        return value

    def _apply_control_overrides(self) -> None:
        try:
            with SessionLocal() as session:
                rows = session.query(Setting).filter(Setting.key.like("control.%")).all()
        except Exception:
            return
        if not rows:
            return
        overrides: Dict[str, object] = {}
        for row in rows:
            if not row.key or not row.key.startswith("control."):
                continue
            suffix = row.key.split(".", 1)[1]
            if not suffix:
                continue
            value = self._coerce_control_value(suffix, row.value)
            if value is not None:
                overrides[suffix] = value
        if overrides:
            CONTROL.update(overrides)

    def _persist_control_overrides(self, control: Dict[str, object]) -> None:
        try:
            with SessionLocal() as session:
                for key, value in control.items():
                    session.merge(Setting(key=f"control.{key}", value=str(value)))
                session.commit()
        except Exception:
            pass

    def _apply_heating_overrides(self) -> None:
        if not isinstance(HEATING, dict):
            return
        try:
            with SessionLocal() as session:
                row = session.get(Setting, "heating")
        except Exception:
            return
        if not row or not row.value:
            return
        try:
            data = json.loads(row.value)
        except json.JSONDecodeError:
            return
        if isinstance(data, dict):
            HEATING.update(data)

    def _persist_heating_overrides(self, payload: Dict[str, object]) -> None:
        if not isinstance(HEATING, dict):
            return
        try:
            with SessionLocal() as session:
                session.merge(Setting(key="heating", value=json.dumps(payload)))
                session.commit()
        except Exception:
            pass


    def _persist_setting(self, key: str, value: dict) -> None:
        try:
            with SessionLocal() as session:
                session.merge(Setting(key=key, value=json.dumps(value)))
                session.commit()
        except Exception:
            pass


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

    def _enforce_vent_target(self, vent_id: int, requested_pct: float) -> float:
        try:
            target = float(requested_pct)
        except (TypeError, ValueError):
            target = 0.0
        target = max(0.0, min(100.0, target))
        for gid in self._vent_to_groups.get(vent_id, []):
            group = self._groups.get(gid)
            if not group:
                continue
            override = group.get("target_override")
            force_close = group.get("force_close", False)
            if override is None:
                continue
            if force_close or target > override:
                target = override
        return max(0.0, min(100.0, target))

    def _auto_adjustment_needed(self, target_pct: float) -> bool:
        for group in self._groups.values():
            for vid in group.get("vents", []):
                vent = self.vents.get(vid)
                if not vent or not vent.available:
                    continue
                effective = self._enforce_vent_target(vent.id, target_pct)
                if abs(effective - vent.position) > self._tolerance:
                    return True
        return False

    async def _move_group_step(self, group_id: str, target_pct: float, step: float, closing: bool) -> bool:
        group = self._groups.get(group_id)
        if not group:
            return False
        tasks = []
        force_close = group.get("force_close", False)
        for vid in group.get("vents", []):
            vent = self.vents.get(vid)
            if not vent or not vent.available:
                continue
            effective_target = self._enforce_vent_target(vent.id, target_pct)
            diff = effective_target - vent.position
            if abs(diff) <= self._tolerance:
                continue
            if closing and diff > 0 and not force_close:
                continue
            if not closing and diff < 0 and not force_close:
                continue
            step_size = min(step, abs(diff))
            if diff > 0:
                next_pct = min(effective_target, vent.position + step_size)
            else:
                next_pct = max(effective_target, vent.position - step_size)
            if abs(next_pct - vent.position) <= self._tolerance:
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
            s.merge(RuntimeState(key="mode", value=self.mode))
            s.commit()
        if prev != mode:
            self._log_event(
                "MODE_CHANGE",
                meta={"mode": self.mode},
                category="mode",
            )
            if mode == "manual":
                # zatrzymaj wszystkie ruchy i wyrĂłwnaj cele do bieĹĽÄ…cej pozycji
                async def _stop_all():
                    await asyncio.gather(*[v.stop() for v in self.vents.values()])
                if self._async_loop:
                    asyncio.run_coroutine_threadsafe(_stop_all(), self._async_loop)
                for v in self.vents.values():
                    v.user_target = float(v.position)
                    self._save_vent_state(v.id)
                self._last_auto_target = None
            else:
                self._last_auto_target = None
                self.calibrate_all()

    def _compute_auto_target(self, s: dict) -> float:
        target_temp = self._resolve_environment_target(datetime.now())
        hum_thr     = CONTROL.get("humidity_thr", 70.0)
        diff_pct    = CONTROL.get("temp_diff_percent", 5.0)
        diff = s["internal_temp"] - target_temp
        # prosta proporcja: temp_diff_percent% / 1Ä‚â€šĂ‚Â°C
        pct = 0.0
        if diff > 0 and s["external_temp"] < s["internal_temp"]:
            pct = min(100.0, diff * diff_pct)
        elif diff < 0 and s["external_temp"] > s["internal_temp"]:
            pct = min(100.0, abs(diff) * diff_pct)
        # wilgotnoĂ„Ä…Ă˘â‚¬ĹźÄ‚â€žĂ˘â‚¬Ë‡ wymusza min. wietrzenie (gdy bez deszczu/wiatru krytycznego Ä‚ËĂ˘â€šÂ¬Ă˘â‚¬Ĺ› sprawdzimy niĂ„Ä…Ă„Ëťej)
        if s["internal_hum"] > hum_thr and pct < CONTROL.get("min_open_hum_percent", 20.0):
            pct = CONTROL.get("min_open_hum_percent", 20.0)
        co2_thr = CONTROL.get("co2_thr_ppm")
        try:
            co2_thr_val = float(co2_thr) if co2_thr is not None else None
        except (TypeError, ValueError):
            co2_thr_val = None
        try:
            co2_value = float(s.get("internal_co2"))
        except (TypeError, ValueError):
            co2_value = None
        self._update_co2_alert(co2_value, co2_thr_val)
        if co2_thr_val is not None and co2_value is not None and co2_value > co2_thr_val:
            co2_open_raw = CONTROL.get("min_open_co2_percent", CONTROL.get("min_open_hum_percent", 20.0))
            try:
                co2_open = float(co2_open_raw)
            except (TypeError, ValueError):
                co2_open = float(CONTROL.get("min_open_hum_percent", 20.0))
            co2_open = max(0.0, min(100.0, co2_open))
            if pct < co2_open:
                pct = co2_open
        return pct

    def _apply_safety(self, base_pct: float, s: dict, manual: bool) -> float:
        risk = CONTROL.get("wind_risk_ms", 10.0)
        crit = CONTROL.get("wind_crit_ms", 20.0)
        lim  = CONTROL.get("risk_open_limit_percent", 50.0)
        rain = s["rain"] > CONTROL.get("rain_threshold", 0.5)
        allow_override = CONTROL.get("allow_humidity_override", False)
        # krytyk: domyĂ„Ä…Ă˘â‚¬Ĺźlnie zamknij wszystko; opcjonalna szczelina przy wilgotnoĂ„Ä…Ă˘â‚¬Ĺźci
        if s["wind_speed"] >= crit or rain:
            if allow_override and s["internal_hum"] > CONTROL.get("humidity_thr", 70.0):
                return CONTROL.get("crit_hum_crack_percent", 10.0)
            return 0.0
        # ryzykowny wiatr: ogranicz max
        if s["wind_speed"] >= risk and base_pct > lim:
            return lim
        if not manual and not self._is_heating_enabled():
            if self._is_nighttime(datetime.now()):
                night_cap = self._night_max_open
                if night_cap is not None and base_pct > night_cap:
                    return night_cap
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
        self._manual_lock = asyncio.Lock()
        while self._running:
            try:
                # zbierz Ă„Ä…Ă˘â‚¬Ĺźrednie: z MQTT i RS485 (Ă„Ä…Ă˘â‚¬ĹˇÄ‚â€žĂ˘â‚¬Â¦czymy Ä‚ËĂ˘â€šÂ¬Ă˘â‚¬Ĺ› preferuj RS485 jeĂ„Ä…Ă˘â‚¬Ĺźli skonfigurowany)
                s1 = sensor_bus.averages()
                sources = {key: 'mqtt' for key, val in s1.items() if val is not None}
                s2 = self.rs485.averages()
                for k, v in s2.items():
                    if v is not None:
                        s1[k] = v
                        sources[k] = 'rs485'
                merged = test_mode.apply_overrides(s1)
                if merged is not s1:
                    for key, value in merged.items():
                        if key not in s1 or merged[key] != s1.get(key):
                            sources[key] = 'override'
                    s1 = merged
                if s1.get('rain') is None:
                    s1['rain'] = 0.0
                    sources.setdefault('rain', 'default')
                self._last_env = dict(s1)
                self._last_env_snapshot = {'sensors': dict(s1), 'sources': sources}
                self._update_group_wind_state(self._last_env)
                required_keys = ('internal_temp', 'external_temp', 'internal_hum', 'wind_speed')
                missing_required = any(s1.get(key) is None for key in required_keys)
                if missing_required:
                    time.sleep(CONTROL.get('controller_loop_s', 1.0))
                    continue
                self._handle_heating(self._last_env)
                # tryb
                if self.mode == "auto":
                    base = self._compute_auto_target(s1)
                    target = self._apply_safety(base, s1, manual=False)
                    needs_adjustment = self._auto_adjustment_needed(target)
                    if (self._last_auto_target is None
                            or abs(target - self._last_auto_target) >= 1.0
                            or needs_adjustment):
                        critical = s1["wind_speed"] >= CONTROL.get("wind_crit_ms", 20.0) or s1["rain"] > CONTROL.get("rain_threshold", 0.5)
                        self._async_loop.run_until_complete(self._auto_move_to(target, critical))
                        for vid in self.vents:
                            self.vents[vid].user_target = target
                            self._save_vent_state(vid)
                        self._last_auto_target = target
                else:
                    # manual Ä‚ËĂ˘â€šÂ¬Ă˘â‚¬Ĺ› tylko bezpieczeĂ„Ä…Ă˘â‚¬Ĺľstwo
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
    def _submit_manual(self, coro_func):
        if not self._async_loop:
            return False
        async def runner():
            lock = self._manual_lock
            if lock is not None:
                async with lock:
                    await coro_func()
            else:
                await coro_func()
        asyncio.run_coroutine_threadsafe(runner(), self._async_loop)
        return True

    def manual_set_all(self, pct: float):
        self.set_mode("manual")
        async def _task():
            await self._move_in_batches(pct)
            for v in self.vents.values():
                if not v.available:
                    continue
                effective = self._enforce_vent_target(v.id, pct)
                v.user_target = effective
                self._save_vent_state(v.id)
        if not self._submit_manual(_task):
            return False
        try:
            test_mode.record_manual_action({"type": "manual_all", "targets": [vent.id for vent in self.vents.values()], "value": float(pct)})
        except Exception:  # pragma: no cover - diagnostics only
            pass
        self._log_event(
            "MANUAL_ACTION",
            meta={
                "scope": "all",
                "value": float(pct),
                "targets": [vent.id for vent in self.vents.values()],
            },
            category="mode",
        )
        return True

    def manual_set_group(self, group_id: str, pct: float) -> bool:
        self.set_mode("manual")
        group = self._groups.get(group_id)
        if not group:
            return False

        async def _task():
            for vid in group.get("vents", []):
                vent = self.vents.get(vid)
                if not vent or not vent.available:
                    continue
                effective = self._enforce_vent_target(vent.id, pct)
                if abs(effective - vent.position) >= self._tolerance:
                    await vent.move_to(effective)
                vent.user_target = effective
                self._save_vent_state(vent.id)

        if not self._submit_manual(_task):
            return False
        try:
            test_mode.record_manual_action({"type": "manual_group", "group_id": group_id, "targets": list(group.get("vents", [])), "value": float(pct)})
        except Exception:  # pragma: no cover - diagnostics only
            pass
        self._log_event(
            "MANUAL_ACTION",
            meta={
                "scope": "group",
                "group": group_id,
                "value": float(pct),
                "targets": list(group.get("vents", [])),
            },
            category="mode",
        )
        return True

    def manual_set_one(self, vent_id: int, pct: float):
        self.set_mode("manual")
        vent = self.vents.get(vent_id)
        if not vent:
            return False

        async def _task():
            if not vent.available:
                return
            effective = self._enforce_vent_target(vent.id, pct)
            if abs(effective - vent.position) >= self._tolerance:
                await vent.move_to(effective)
            vent.user_target = effective
            self._save_vent_state(vent.id)

        if not self._submit_manual(_task):
            return False
        try:
            test_mode.record_manual_action({"type": "manual_vent", "targets": [vent_id], "value": float(pct)})
        except Exception:  # pragma: no cover - diagnostics only
            pass
        self._log_event(
            "MANUAL_ACTION",
            meta={
                "scope": "vent",
                "vent": vent_id,
                "value": float(pct),
            },
            category="mode",
        )
        return True

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
        heating: Optional[dict] = None,
        vents: Optional[List[dict]] = None,
        external: Optional[dict] = None,
        boneio_devices: Optional[List[dict]] = None,
    ) -> None:
        schedule_dirty = False
        if control:
            normalized: Dict[str, object] = {}
            for key, value in control.items():
                normalized[key] = self._coerce_control_value(key, value)
            CONTROL.update(normalized)
            self._persist_control_overrides(normalized)
            self._tolerance = float(CONTROL.get('ignore_delta_percent', 0.5)) or 0.5
            schedule_dirty = True
        if heating:
            sanitized = self._sanitize_heating_config(heating)
            if sanitized:
                HEATING.update(sanitized)
                self._persist_heating_overrides(sanitized)
                schedule_dirty = True
        if external:
            EXTERNAL_CONNECTION.update(external)
            self._persist_setting('external_connection', external)
        if boneio_devices is not None:
            BONEIOS.clear()
            BONEIOS.extend(boneio_devices)
            self._persist_setting('boneio_devices', boneio_devices)
        if vents is not None:
            VENTS.clear()
            VENTS.extend(vents)
            self._load_vents_from_config(vents)
            self._load_state_from_db()
            schedule_dirty = True
        if vent_groups is not None or vent_plan is not None:
            if vent_groups is not None:
                VENT_GROUPS.clear()
                VENT_GROUPS.extend(vent_groups)
            groups_cfg = vent_groups if vent_groups is not None else self.export_groups()
            plan_cfg = vent_plan if isinstance(vent_plan, dict) else self.export_plan()
            stages_cfg = plan_cfg.get('stages', [])
            close_strategy = plan_cfg.get('close_strategy')
            if close_strategy is None:
                close_strategy = plan_cfg.get('close_strategy_flag')
            if vent_plan is not None:
                VENT_PLAN_STAGES.clear()
                VENT_PLAN_STAGES.extend(stages_cfg)
                strategy_norm = self._normalize_close_strategy(close_strategy, self._close_strategy)
                global VENT_PLAN_CLOSE_STRATEGY
                VENT_PLAN_CLOSE_STRATEGY = strategy_norm
            self._configure_plan(groups_cfg, stages_cfg, close_strategy)
        if schedule_dirty:
            self._refresh_schedules()













