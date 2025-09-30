# -*- coding: utf-8 -*-
"""Helper utilities for validating and exporting installer configuration data."""
from __future__ import annotations

from typing import Any, Dict, Iterable, List, Optional

from backend.core.config import (
    CONTROL,
    HEATING,
    VENTS,
    VENT_GROUPS,
    VENT_PLAN_STAGES,
    VENT_PLAN_CLOSE_STRATEGY,
    EXTERNAL_CONNECTION,
    BONEIOS,
)


from backend.core.installer_schemas import (
    ControlFieldSchema,
    ControlSettingsPayload,
    HeatingConfigPayload,
    VentConfigPayload,
    VentGroupPayload,
    VentPlanPayload,
    ExternalConnectionPayload,
    BoneIODeviceConfigPayload,
    InstallerConfigSnapshot,
)


class ConfigValidationError(ValueError):
    """Raised when incoming configuration payload is invalid."""

    def __init__(self, message: str, field: Optional[str] = None):
        super().__init__(message)
        self.field = field


CONTROL_FIELD_DEFINITIONS: Dict[str, Dict[str, Any]] = {
    # Dashboard visible controls
    "target_temp_c": {"type": float, "min": -20.0, "max": 50.0, "category": "dashboard"},
    "day_target_temp_c": {"type": float, "min": -20.0, "max": 50.0, "category": "dashboard"},
    "night_target_temp_c": {"type": float, "min": -20.0, "max": 50.0, "category": "dashboard"},
    "humidity_thr": {"type": float, "min": 0.0, "max": 100.0, "category": "dashboard"},
    "co2_thr_ppm": {"type": float, "min": 0.0, "max": 5000.0, "category": "dashboard"},
    "min_open_co2_percent": {"type": float, "min": 0.0, "max": 100.0, "category": "dashboard"},
    "min_open_hum_percent": {"type": float, "min": 0.0, "max": 100.0, "category": "dashboard"},
    "wind_risk_ms": {"type": float, "min": 0.0, "max": 50.0, "category": "dashboard"},
    "wind_crit_ms": {"type": float, "min": 0.0, "max": 60.0, "category": "dashboard"},
    "rain_threshold": {"type": float, "min": 0.0, "max": 10.0, "category": "dashboard"},
    "night_max_open_percent": {"type": float, "min": 0.0, "max": 100.0, "category": "dashboard"},
    "allow_humidity_override": {"type": bool, "category": "dashboard"},

    # Advanced/hidden controls
    "controller_loop_s": {"type": float, "min": 0.1, "max": 60.0, "category": "advanced"},
    "scheduler_loop_s": {"type": float, "min": 1.0, "max": 600.0, "category": "advanced"},
    "flush_hour": {"type": int, "min": 0, "max": 23, "category": "advanced"},
    "calibration_hour": {"type": int, "min": 0, "max": 23, "category": "advanced"},
    "temp_diff_percent": {"type": float, "min": 0.1, "max": 100.0, "category": "advanced"},
    "step_percent": {"type": float, "min": 1.0, "max": 100.0, "category": "advanced"},
    "step_delay_s": {"type": float, "min": 0.0, "max": 600.0, "category": "advanced"},
    "group_delay_s": {"type": float, "min": 0.0, "max": 600.0, "category": "advanced"},
    "crit_hum_crack_percent": {"type": float, "min": 0.0, "max": 100.0, "category": "advanced"},
    "risk_open_limit_percent": {"type": float, "min": 0.0, "max": 100.0, "category": "advanced"},
    "wind_lock_enabled": {"type": bool, "category": "advanced"},
    "day_start": {"type": str, "category": "advanced"},
    "night_start": {"type": str, "category": "advanced"},
}




def _control_type_label(meta: Dict[str, Any], value: Any) -> str:
    field_type = meta.get("type")
    if field_type is bool or isinstance(value, bool):
        return "bool"
    if field_type is int or (isinstance(value, int) and not isinstance(value, bool)):
        return "int"
    if field_type is float or isinstance(value, float):
        return "float"
    return "str"


def _coerce_bool(value: Any) -> bool:
    if isinstance(value, bool):
        return value
    if isinstance(value, str):
        lowered = value.strip().lower()
        if lowered in {"1", "true", "yes", "on"}:
            return True
        if lowered in {"0", "false", "no", "off"}:
            return False
    return bool(value)


def _coerce_number(value: Any, numeric_type: type) -> float | int:
    if isinstance(value, (int, float)):
        return numeric_type(value)
    if isinstance(value, str) and value.strip() != "":
        return numeric_type(float(value))
    raise ConfigValidationError("Wymagana wartość liczbowa")


def _numeric_bounds(field: str, value: float | int, meta: Dict[str, Any]) -> float | int:
    minimum = meta.get("min")
    maximum = meta.get("max")
    if minimum is not None and value < minimum:
        raise ConfigValidationError(
            f"Wartość pola '{field}' nie może być mniejsza niż {minimum}", field
        )
    if maximum is not None and value > maximum:
        raise ConfigValidationError(
            f"Wartość pola '{field}' nie może być większa niż {maximum}", field
        )
    return value


def sanitize_control_payload(payload: Dict[str, Any]) -> Dict[str, Any]:
    sanitized: Dict[str, Any] = {}
    for key, value in payload.items():
        meta = CONTROL_FIELD_DEFINITIONS.get(key, {"type": type(CONTROL.get(key)), "category": "advanced"})
        try:
            field_type = meta.get("type")
            if field_type is bool:
                coerced = _coerce_bool(value)
            elif field_type is int:
                coerced = _numeric_bounds(key, _coerce_number(value, int), meta)
            elif field_type is float:
                coerced = _numeric_bounds(key, _coerce_number(value, float), meta)
            else:
                coerced = str(value).strip()
        except ConfigValidationError as exc:
            exc.field = key
            raise
        except Exception as exc:
            raise ConfigValidationError(f"Nieprawidłowa wartość dla pola '{key}'", key) from exc
        sanitized[key] = coerced
    return sanitized


def split_control_settings() -> Dict[str, Dict[str, Any]]:
    dashboard: Dict[str, Any] = {}
    advanced: Dict[str, Any] = {}
    for key, value in CONTROL.items():
        meta = CONTROL_FIELD_DEFINITIONS.get(key, {"category": "advanced"})
        category = meta.get("category", "advanced")
        if category == "dashboard":
            dashboard[key] = value
        else:
            advanced[key] = value
    return {"dashboard": dashboard, "advanced": advanced}


def _control_field_from_meta(key: str, meta: Dict[str, Any], value: Any) -> ControlFieldSchema:
    return ControlFieldSchema(
        key=key,
        value=value,
        category=meta.get("category", "advanced"),
        type=_control_type_label(meta, value),
        min=meta.get("min"),
        max=meta.get("max"),
        description=meta.get("description"),
    )


def build_control_fields() -> Dict[str, Any]:
    sections: Dict[str, List[ControlFieldSchema]] = {"dashboard": [], "advanced": []}
    seen: set[str] = set()

    for key, meta in CONTROL_FIELD_DEFINITIONS.items():
        current_value = CONTROL.get(key)
        field = _control_field_from_meta(key, meta, current_value)
        sections[field.category].append(field)
        seen.add(key)

    for key, value in CONTROL.items():
        if key in seen:
            continue
        meta = CONTROL_FIELD_DEFINITIONS.get(key, {"category": "advanced"})
        field = _control_field_from_meta(key, meta, value)
        sections[field.category].append(field)
        seen.add(key)

    for bucket in sections.values():
        bucket.sort(key=lambda item: item.key)

    flat: Dict[str, Any] = {field.key: field.value for field in sections["dashboard"]}
    flat.update({field.key: field.value for field in sections["advanced"]})

    return {"dashboard": sections["dashboard"], "advanced": sections["advanced"], "flat": flat}


def sanitize_heating_payload(payload: Dict[str, Any]) -> Dict[str, Any]:
    if not isinstance(payload, dict):
        raise ConfigValidationError("Payload ogrzewania musi być obiektem JSON")
    sanitized: Dict[str, Any] = {}
    if "enabled" not in payload:
        raise ConfigValidationError("Pole 'enabled' jest wymagane", "enabled")
    sanitized["enabled"] = _coerce_bool(payload.get("enabled"))

    def _string_opt(key: str) -> None:
        if key not in payload:
            return
        value = payload.get(key)
        if value is None:
            sanitized[key] = None
            return
        value_str = str(value).strip()
        sanitized[key] = value_str or None

    for key in ("topic", "payload_on", "payload_off"):
        _string_opt(key)

    def _float_opt(key: str, allow_negative: bool = False) -> None:
        if key not in payload:
            return
        value = payload.get(key)
        if value in (None, ""):
            sanitized[key] = None
            return
        number = _coerce_number(value, float)
        if not allow_negative and number < 0:
            raise ConfigValidationError(f"Pole '{key}' nie może być ujemne", key)
        sanitized[key] = number

    for key in ("day_target_c", "night_target_c", "hysteresis_c"):
        _float_opt(key)

    def _time_opt(key: str) -> None:
        if key not in payload:
            return
        value = payload.get(key)
        if value in (None, ""):
            sanitized[key] = None
            return
        value_str = str(value).strip()
        if len(value_str) != 5 or value_str[2] != ':' or not value_str.replace(':', '').isdigit():
            raise ConfigValidationError(f"Pole '{key}' musi być w formacie HH:MM", key)
        hour, minute = value_str.split(':')
        hour_int = int(hour)
        minute_int = int(minute)
        if not (0 <= hour_int <= 23 and 0 <= minute_int <= 59):
            raise ConfigValidationError(f"Pole '{key}' musi być w formacie HH:MM", key)
        sanitized[key] = f"{hour_int:02d}:{minute_int:02d}"

    for key in ("day_start", "night_start"):
        _time_opt(key)

    return sanitized


def sanitize_external_payload(payload: Dict[str, Any]) -> Dict[str, Any]:
    if not isinstance(payload, dict):
        raise ConfigValidationError("Payload konfiguracji serwera zewnętrznego musi być obiektem JSON")
    sanitized: Dict[str, Any] = {}
    sanitized["enabled"] = _coerce_bool(payload.get("enabled", EXTERNAL_CONNECTION.get("enabled", False)))
    protocol = str(payload.get("protocol", EXTERNAL_CONNECTION.get("protocol", "https"))).strip().lower()
    if protocol not in {"http", "https"}:
        raise ConfigValidationError("Dozwolone protokoły to http lub https", "protocol")
    sanitized["protocol"] = protocol
    host = str(payload.get("host", EXTERNAL_CONNECTION.get("host", ""))).strip()
    if sanitized["enabled"] and not host:
        raise ConfigValidationError("Adres host jest wymagany gdy połączenie jest aktywne", "host")
    sanitized["host"] = host
    try:
        port = int(payload.get("port", EXTERNAL_CONNECTION.get("port", 443)))
    except Exception as exc:
        raise ConfigValidationError("Port musi być liczbą", "port") from exc
    if not (0 < port < 65536):
        raise ConfigValidationError("Port musi być pomiędzy 1 a 65535", "port")
    sanitized["port"] = port
    path_value = str(payload.get("path", EXTERNAL_CONNECTION.get("path", "/"))).strip() or "/"
    if not path_value.startswith("/"):
        path_value = "/" + path_value
    sanitized["path"] = path_value
    token = payload.get("token", EXTERNAL_CONNECTION.get("token", ""))
    sanitized["token"] = str(token) if token is not None else ""
    return sanitized


def sanitize_wind_ranges(ranges: Iterable[Any]) -> List[List[float]]:
    cleaned: List[List[float]] = []
    for entry in ranges:
        if isinstance(entry, dict):
            start = entry.get("start", entry.get("from"))
            end = entry.get("end", entry.get("to"))
        elif isinstance(entry, (list, tuple)) and len(entry) >= 2:
            start, end = entry[0], entry[1]
        else:
            raise ConfigValidationError("Zakresy wiatru muszą mieć postać [start, stop]", "wind_upwind_deg")
        start_val = float(start)
        end_val = float(end)
        if not (0.0 <= start_val <= 360.0 and 0.0 <= end_val <= 360.0):
            raise ConfigValidationError("Kąt wiatru powinien być w zakresie 0-360", "wind_upwind_deg")
        cleaned.append([start_val, end_val])
    return cleaned


def sanitize_groups_payload(groups: List[Dict[str, Any]], valid_vent_ids: Iterable[int]) -> List[Dict[str, Any]]:
    if not isinstance(groups, list):
        raise ConfigValidationError("Grupy muszą być listą", "groups")
    sanitized: List[Dict[str, Any]] = []
    vent_id_set = set(int(v) for v in valid_vent_ids)
    for index, group in enumerate(groups):
        if not isinstance(group, dict):
            raise ConfigValidationError("Każda grupa musi być obiektem JSON", f"groups[{index}]")
        gid = str(group.get("id") or f"group_{index + 1}").strip()
        name = str(group.get("name") or gid).strip()
        vents_raw = group.get("vents", [])
        if not isinstance(vents_raw, list) or not vents_raw:
            raise ConfigValidationError("Grupa musi zawierać co najmniej jeden wietrznik", f"groups[{gid}]")
        vents: List[int] = []
        for item in vents_raw:
            try:
                vid = int(item)
            except Exception as exc:
                raise ConfigValidationError("Identyfikator wietrznika musi być liczbą", f"groups[{gid}].vents") from exc
            if vid not in vent_id_set:
                raise ConfigValidationError(f"Wietrznik {vid} nie istnieje", f"groups[{gid}].vents")
            if vid not in vents:
                vents.append(vid)
        wind_ranges = group.get("wind_upwind_deg") or []
        sanitized_group = {
            "id": gid,
            "name": name,
            "vents": vents,
            "wind_lock_enabled": _coerce_bool(group.get("wind_lock_enabled", True)),
        }
        if wind_ranges:
            sanitized_group["wind_upwind_deg"] = sanitize_wind_ranges(wind_ranges)
        close_percent = group.get("wind_lock_close_percent")
        if close_percent not in (None, ""):
            number = float(close_percent)
            if not (0.0 <= number <= 100.0):
                raise ConfigValidationError("Pozycja blokady musi być w zakresie 0-100%", f"groups[{gid}].wind_lock_close_percent")
            sanitized_group["wind_lock_close_percent"] = number
        sanitized.append(sanitized_group)
    return sanitized


def sanitize_plan_payload(plan: Dict[str, Any], valid_group_ids: Iterable[str]) -> Dict[str, Any]:
    if not isinstance(plan, dict):
        raise ConfigValidationError("Plan musi być obiektem JSON", "plan")
    group_set = {str(g) for g in valid_group_ids}
    stages_raw = plan.get("stages", []) or []
    if not isinstance(stages_raw, list):
        raise ConfigValidationError("Plan musi zawierać listę etapów", "plan.stages")
    sanitized_stages: List[Dict[str, Any]] = []
    for index, raw_stage in enumerate(stages_raw):
        if not isinstance(raw_stage, dict):
            raise ConfigValidationError("Etap planu musi być obiektem JSON", f"plan.stages[{index}]")
        sid = str(raw_stage.get("id") or f"stage_{index + 1}").strip()
        name = str(raw_stage.get("name") or sid).strip()
        mode = str(raw_stage.get("mode", "serial")).strip().lower()
        if mode not in {"serial", "parallel"}:
            raise ConfigValidationError("Tryb etapu musi być 'serial' lub 'parallel'", f"plan.stages[{sid}].mode")
        try:
            step = float(raw_stage.get("step_percent", 100))
        except Exception as exc:
            raise ConfigValidationError("Krok etapu musi być liczbą", f"plan.stages[{sid}].step_percent") from exc
        delay = float(raw_stage.get("delay_s", 0))
        if step <= 0 or step > 100:
            raise ConfigValidationError("Krok etapu musi być w zakresie 0-100%", f"plan.stages[{sid}].step_percent")
        if delay < 0:
            raise ConfigValidationError("Opóźnienie nie może być ujemne", f"plan.stages[{sid}].delay_s")
        stage_groups = raw_stage.get("groups", []) or []
        if not stage_groups:
            raise ConfigValidationError("Etap musi zawierać przynajmniej jedną grupę", f"plan.stages[{sid}].groups")
        validated_groups: List[str] = []
        for group_id in stage_groups:
            gid = str(group_id)
            if gid not in group_set:
                raise ConfigValidationError(f"Grupa '{gid}' nie istnieje", f"plan.stages[{sid}].groups")
            if gid not in validated_groups:
                validated_groups.append(gid)
        stage_data = {
            "id": sid,
            "name": name,
            "mode": mode,
            "step_percent": step,
            "delay_s": delay,
            "groups": validated_groups,
        }
        raw_close = raw_stage.get("close_strategy")
        if raw_close is None:
            raw_close = raw_stage.get("close_strategy_flag")
        if raw_close is not None:
            close_value = raw_close if isinstance(raw_close, str) else str(raw_close)
            if str(close_value).strip().lower() in {"1", "lifo", "true"}:
                stage_data["close_strategy_flag"] = 1
            else:
                stage_data["close_strategy_flag"] = 0
        sanitized_stages.append(stage_data)
    close_strategy = plan.get("close_strategy")
    if close_strategy is None:
        close_strategy = plan.get("close_strategy_flag", VENT_PLAN_CLOSE_STRATEGY)
    close_normalized = VENT_PLAN_CLOSE_STRATEGY
    if isinstance(close_strategy, str):
        close_normalized = "lifo" if close_strategy.strip().lower() in {"1", "lifo", "true"} else "fifo"
    elif isinstance(close_strategy, (int, float)):
        close_normalized = "lifo" if int(close_strategy) == 1 else "fifo"
    return {
        "close_strategy": close_normalized,
        "stages": sanitized_stages,
    }


def sanitize_boneio_payload(devices: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    if not isinstance(devices, list):
        raise ConfigValidationError("Lista urzadzen BoneIO musi byc tablica", "boneio_devices")
    sanitized: List[Dict[str, Any]] = []
    seen_ids: set[str] = set()
    seen_topics: set[str] = set()
    for index, raw in enumerate(devices):
        if not isinstance(raw, dict):
            raise ConfigValidationError("Konfiguracja urzadzenia musi byc obiektem JSON", f"boneio_devices[{index}]")
        dev_id = str(raw.get("id") or "").strip()
        if not dev_id:
            raise ConfigValidationError("Pole 'id' jest wymagane", f"boneio_devices[{index}].id")
        if dev_id in seen_ids:
            raise ConfigValidationError(f"Id urzadzenia '{dev_id}' jest zduplikowane", f"boneio_devices[{index}].id")
        base_topic = str(raw.get("base_topic") or "").strip()
        if not base_topic:
            raise ConfigValidationError("Pole 'base_topic' jest wymagane", f"boneio_devices[{dev_id}].base_topic")
        if base_topic in seen_topics:
            raise ConfigValidationError(f"Topic '{base_topic}' zostal zdefiniowany wielokrotnie", f"boneio_devices[{dev_id}].base_topic")
        entry: Dict[str, Any] = {"id": dev_id, "base_topic": base_topic}
        description = raw.get("description")
        if description not in (None, ""):
            entry["description"] = str(description).strip()
        availability = raw.get("availability_topic")
        if availability not in (None, ""):
            entry["availability_topic"] = str(availability).strip()
        sanitized.append(entry)
        seen_ids.add(dev_id)
        seen_topics.add(base_topic)
    return sanitized

def sanitize_vents_payload(vents: List[Dict[str, Any]], valid_devices: Optional[Iterable[str]] = None) -> List[Dict[str, Any]]:
    if not isinstance(vents, list):
        raise ConfigValidationError("Lista wietrzników musi być tablicą", "vents")
    sanitized: List[Dict[str, Any]] = []
    used_ids: set[int] = set()
    device_whitelist: set[str] = set()
    if valid_devices:
        for item in valid_devices:
            if item is None:
                continue
            device_id = str(item).strip()
            if device_id:
                device_whitelist.add(device_id)
    elif BONEIOS:
        for entry in BONEIOS:
            device_id = str(entry.get("id") or "").strip()
            if device_id:
                device_whitelist.add(device_id)
    for index, raw in enumerate(vents):
        if not isinstance(raw, dict):
            raise ConfigValidationError("Konfiguracja wietrznika musi być obiektem JSON", f"vents[{index}]")
        try:
            vid = int(raw.get("id"))
        except Exception as exc:
            raise ConfigValidationError("Pole 'id' musi być liczbą", f"vents[{index}].id") from exc
        if vid in used_ids:
            raise ConfigValidationError(f"Identyfikator wietrznika {vid} jest duplikatem", f"vents[{index}].id")
        used_ids.add(vid)
        name = str(raw.get("name") or f"Vent {vid}").strip()
        if device_whitelist:
            boneio_raw = raw.get("boneio_device")
            boneio_device = str(boneio_raw).strip() if boneio_raw not in (None, "") else ""
            if not boneio_device:
                raise ConfigValidationError("Wybierz urządzenie BoneIO", f"vents[{vid}].boneio_device")
            if boneio_device not in device_whitelist:
                raise ConfigValidationError(
                    f"Nieznane urządzenie BoneIO '{boneio_device}'",
                    f"vents[{vid}].boneio_device",
                )
        else:
            boneio_device = str(raw.get("boneio_device") or "boneio_main").strip() or "boneio_main"
        try:
            travel_time = float(raw.get("travel_time_s", 30.0))
        except Exception as exc:
            raise ConfigValidationError("Pole 'travel_time_s' musi być liczbą", f"vents[{vid}].travel_time_s") from exc
        if travel_time <= 0:
            raise ConfigValidationError("Czas ruchu musi być dodatni", f"vents[{vid}].travel_time_s")
        topics = raw.get("topics") or {}
        if not isinstance(topics, dict) or not topics.get("up") or not topics.get("down"):
            raise ConfigValidationError("Wietrznik wymaga tematów 'up' i 'down'", f"vents[{vid}].topics")
        vent_data: Dict[str, Any] = {
            "id": vid,
            "name": name,
            "boneio_device": boneio_device,
            "travel_time_s": travel_time,
            "topics": {
                "up": str(topics["up"]).strip(),
                "down": str(topics["down"]).strip(),
            },
        }
        error_topic = topics.get("error_in")
        if error_topic:
            vent_data["topics"]["error_in"] = str(error_topic).strip()
        for optional_key in ("reverse_pause_s", "min_move_s", "calibration_buffer_s", "ignore_delta_percent"):
            if optional_key in raw and raw[optional_key] not in (None, ""):
                vent_data[optional_key] = float(raw[optional_key])
        sanitized.append(vent_data)
    return sanitized


def export_boneio_configuration() -> List[Dict[str, Any]]:
    return [dict(device) for device in BONEIOS]


def boneio_payload_to_models(devices: List[Dict[str, Any]]) -> List[BoneIODeviceConfigPayload]:
    sanitized = sanitize_boneio_payload(devices)
    return [BoneIODeviceConfigPayload(**item) for item in sanitized]


def export_vent_configuration() -> List[Dict[str, Any]]:
    return [dict(vent) for vent in VENTS]


def export_groups_configuration() -> List[Dict[str, Any]]:
    return [dict(group) for group in VENT_GROUPS]


def export_plan_configuration() -> Dict[str, Any]:
    return {
        "close_strategy": VENT_PLAN_CLOSE_STRATEGY,
        "stages": [dict(stage) for stage in VENT_PLAN_STAGES],
    }


def export_heating_configuration() -> Dict[str, Any]:
    return dict(HEATING)


def export_external_configuration() -> Dict[str, Any]:
    return dict(EXTERNAL_CONNECTION)


def control_payload_to_model(payload: Dict[str, Any]) -> ControlSettingsPayload:
    sanitized = sanitize_control_payload(payload)
    return ControlSettingsPayload(values=sanitized)


def heating_payload_to_model(payload: Dict[str, Any]) -> HeatingConfigPayload:
    sanitized = sanitize_heating_payload(payload)
    return HeatingConfigPayload(**sanitized)


def vents_payload_to_models(vents: List[Dict[str, Any]], valid_device_ids: Optional[Iterable[str]] = None) -> List[VentConfigPayload]:
    sanitized = sanitize_vents_payload(vents, valid_device_ids)
    return [VentConfigPayload(**item) for item in sanitized]


def groups_payload_to_models(groups: List[Dict[str, Any]], valid_vent_ids: Iterable[int]) -> List[VentGroupPayload]:
    sanitized = sanitize_groups_payload(groups, valid_vent_ids)
    return [VentGroupPayload(**item) for item in sanitized]


def plan_payload_to_model(plan: Dict[str, Any], valid_group_ids: Iterable[str]) -> VentPlanPayload:
    sanitized = sanitize_plan_payload(plan, valid_group_ids)
    return VentPlanPayload(**sanitized)


def external_payload_to_model(payload: Dict[str, Any]) -> ExternalConnectionPayload:
    sanitized = sanitize_external_payload(payload)
    return ExternalConnectionPayload(**sanitized)


def export_installer_snapshot() -> InstallerConfigSnapshot:
    return InstallerConfigSnapshot(
        control=dict(CONTROL),
        heating=HeatingConfigPayload(**export_heating_configuration()),
        boneio=[BoneIODeviceConfigPayload(**device) for device in export_boneio_configuration()],
        vents=[VentConfigPayload(**vent) for vent in export_vent_configuration()],
        groups=[VentGroupPayload(**group) for group in export_groups_configuration()],
        plan=VentPlanPayload(**export_plan_configuration()),
        external=ExternalConnectionPayload(**export_external_configuration()),
    )


__all__ = [
    "ConfigValidationError",
    "CONTROL_FIELD_DEFINITIONS",
    "split_control_settings",
    "build_control_fields",
    "sanitize_control_payload",
    "sanitize_heating_payload",
    "sanitize_boneio_payload",
    "sanitize_vents_payload",
    "sanitize_groups_payload",
    "sanitize_plan_payload",
    "sanitize_external_payload",
    "control_payload_to_model",
    "heating_payload_to_model",
    "boneio_payload_to_models",
    "vents_payload_to_models",
    "groups_payload_to_models",
    "plan_payload_to_model",
    "external_payload_to_model",
    "export_boneio_configuration",
    "export_vent_configuration",
    "export_groups_configuration",
    "export_plan_configuration",
    "export_heating_configuration",
    "export_external_configuration",
    "export_installer_snapshot",
]
