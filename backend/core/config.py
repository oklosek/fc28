# -*- coding: utf-8 -*-
# backend/core/config.py – konfiguracja aplikacji + settings.yaml
import os
try:
    import yaml
except Exception:  # pragma: no cover
    yaml = None
try:
    from pydantic import BaseSettings
except Exception:  # pragma: no cover
    class BaseSettings:
        def __init__(self, **kwargs):
            for k, v in kwargs.items():
                setattr(self, k, v)
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parents[2]
CONFIG_DIR = BASE_DIR / "config"
DB_DIR = BASE_DIR / "data"
LOG_DIR = BASE_DIR / "logs"

class Settings(BaseSettings):
    # .env
    ADMIN_TOKEN: str = "change_me"
    MQTT_HOST: str = "127.0.0.1"
    MQTT_PORT: int = 1883
    MQTT_USERNAME: str = ""
    MQTT_PASSWORD: str = ""
    # CORS
    cors_allow_origins: list[str] = ["*"]

    # Ścieżki
    db_path: str = str(DB_DIR / "farmcare.sqlite3")
    settings_yaml: str = str(CONFIG_DIR / "settings.yaml")

    class Config:
        env_file = CONFIG_DIR / ".env"

def load_yaml_settings(path: str):
    if yaml is None:
        return {}
    try:
        with open(path, "r", encoding="utf-8") as f:
            data = yaml.safe_load(f)
    except FileNotFoundError:
        return {}
    except Exception as exc:
        print(f"Failed to read settings.yaml: {exc}")
        return {}
    if not isinstance(data, dict):
        return {}
    return data

def ensure_dirs():
    DB_DIR.mkdir(parents=True, exist_ok=True)
    LOG_DIR.mkdir(parents=True, exist_ok=True)

settings = Settings()
yaml_cfg = load_yaml_settings(settings.settings_yaml)


# Pomocnicze
def _parse_close_strategy(value, default='fifo') -> str:
    if isinstance(value, (int, float)):
        return 'lifo' if int(value) == 1 else 'fifo'
    if isinstance(value, str):
        val = value.strip().lower()
        if val in ('fifo', 'lifo'):
            return val
    return default

# Kluczowe parametry z YAML
_RAW_VENT_GROUPS = yaml_cfg.get("vent_groups", [])           # definicje grup wentylacyjnych
_RAW_VENTS = yaml_cfg.get("vents", [])                           # wszystkie wietrzniki (dynamicznie)
VENTS: list[dict] = list(_RAW_VENTS) if isinstance(_RAW_VENTS, list) else []
_RAW_BONEIO = yaml_cfg.get("boneio_devices", [])                # konfiguracja BoneIO
BONEIOS: list[dict] = []
if isinstance(_RAW_BONEIO, list):
    seen_devices = set()
    for idx, raw in enumerate(_RAW_BONEIO, start=1):
        if not isinstance(raw, dict):
            continue
        dev_id = str(raw.get("id") or f"boneio_{idx}").strip()
        if not dev_id:
            dev_id = f"boneio_{idx}"
        if dev_id in seen_devices:
            continue
        base_topic = str(raw.get("base_topic") or "").strip()
        if not base_topic:
            continue
        entry = {"id": dev_id, "base_topic": base_topic}
        description = raw.get("description")
        if isinstance(description, str) and description.strip():
            entry["description"] = description.strip()
        availability = raw.get("availability_topic")
        if isinstance(availability, str) and availability.strip():
            entry["availability_topic"] = availability.strip()
        BONEIOS.append(entry)
        seen_devices.add(dev_id)
VENT_DEFAULTS = yaml_cfg.get("vent_defaults", {})           # domyślne parametry wietrzników
HEATING = yaml_cfg.get("heating", {})                       # konfiguracja ogrzewania
if isinstance(HEATING, dict):
    HEATING.setdefault("enabled", False)
    HEATING.setdefault("topic", None)
    HEATING.setdefault("payload_on", "ON")
    HEATING.setdefault("payload_off", "OFF")
    HEATING.setdefault("day_target_c", None)
    HEATING.setdefault("night_target_c", None)
    HEATING.setdefault("hysteresis_c", 5.0)
    HEATING.setdefault("day_start", "06:00")
    HEATING.setdefault("night_start", "20:00")
EXTERNAL_CONNECTION = yaml_cfg.get("external_connection", {})             # serwer zewnetrzny
if isinstance(EXTERNAL_CONNECTION, dict):
    EXTERNAL_CONNECTION.setdefault("enabled", False)
    EXTERNAL_CONNECTION.setdefault("protocol", "https")
    EXTERNAL_CONNECTION.setdefault("host", "")
    EXTERNAL_CONNECTION.setdefault("port", 443)
    EXTERNAL_CONNECTION.setdefault("path", "/")
    EXTERNAL_CONNECTION.setdefault("token", "")
SENSORS = yaml_cfg.get("sensors", {})                       # mapowanie czujników
RS485_BUSES = yaml_cfg.get("rs485_buses", [])               # dwie magistrale
CONTROL = yaml_cfg.get("control", {})                       # progi, czasy itp.
CONTROL.setdefault("temp_diff_percent", 5.0)
CONTROL.setdefault("day_target_temp_c", CONTROL.get("target_temp_c", 25.0))
CONTROL.setdefault("night_target_temp_c", CONTROL.get("target_temp_c", 25.0))
CONTROL.setdefault("day_start", "06:00")
CONTROL.setdefault("night_start", "20:00")
CONTROL.setdefault("night_max_open_percent", 40.0)
CONTROL.setdefault("wind_lock_enabled", True)
if "co2_thr_ppm" not in CONTROL:
    CONTROL["co2_thr_ppm"] = None
CONTROL.setdefault("min_open_co2_percent", CONTROL.get("min_open_hum_percent", 20.0))
SECURITY = yaml_cfg.get("security", {})                     # polityka WAN/LAN
NETWORK_INTERFACES = yaml_cfg.get("network_interfaces", {})
if not isinstance(NETWORK_INTERFACES, dict):
    NETWORK_INTERFACES = {}
for _role in ("lan", "wan"):
    entry = NETWORK_INTERFACES.get(_role)
    if isinstance(entry, str):
        NETWORK_INTERFACES[_role] = {"name": entry}
    elif entry is None:
        NETWORK_INTERFACES[_role] = {}
UPDATES = yaml_cfg.get("updates", {})
if isinstance(UPDATES, dict):
    UPDATES.setdefault("enabled", False)
    UPDATES.setdefault("manifest_url", "")
    UPDATES.setdefault("check_interval_hours", 24)
    UPDATES.setdefault("apply_script", "")
    UPDATES.setdefault("channel", "stable")
    default_dir = str(BASE_DIR / "updates")
    UPDATES.setdefault("download_dir", default_dir)
else:
    UPDATES = {"enabled": False, "manifest_url": "", "check_interval_hours": 24, "apply_script": "", "channel": "stable", "download_dir": str(BASE_DIR / "updates")}
AVG_WINDOW_S = yaml_cfg.get("sensor_avg_window_s", 5)

# Przygotuj listę grup oraz plan etapów (kompatybilność wsteczna)
VENT_GROUPS: list[dict] = []
for idx, grp in enumerate(_RAW_VENT_GROUPS, start=1):
    gid = grp.get("id") or f"group_{idx}"
    VENT_GROUPS.append({
        "id": gid,
        "name": grp.get("name", f"Group {idx}"),
        "vents": list(grp.get("vents", [])),
    })

VENT_PLAN = yaml_cfg.get("vent_plan") or {}
VENT_PLAN_CLOSE_STRATEGY = _parse_close_strategy(VENT_PLAN.get("close_strategy"), "fifo")
VENT_PLAN_STAGES = VENT_PLAN.get("stages", [])

if not VENT_PLAN_STAGES and VENT_GROUPS:
    fallback_delay = CONTROL.get("group_delay_s", 0)
    for idx, grp in enumerate(VENT_GROUPS, start=1):
        VENT_PLAN_STAGES.append({
            "id": f"stage_{idx}",
            "name": grp["name"],
            "mode": "serial",
            "step_percent": 100,
            "groups": [grp["id"]],
            "delay_s": fallback_delay,
        })

