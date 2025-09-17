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
    MQTT_URL: str = "mqtt://localhost"
    MQTT_HOST: str = "127.0.0.1"
    MQTT_PORT: int = 1883
    MQTT_USERNAME: str = ""
    MQTT_PASSWORD: str = ""
    # API
    API_HOST: str = "0.0.0.0"
    API_PORT: int = 8000
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
VENTS = yaml_cfg.get("vents", [])                           # wszystkie wietrzniki (dynamicznie)
BONEIOS = yaml_cfg.get("boneio_devices", [])                # mapowanie kanałów
VENT_DEFAULTS = yaml_cfg.get("vent_defaults", {})           # domyślne parametry wietrzników
SENSORS = yaml_cfg.get("sensors", {})                       # mapowanie czujników
RS485_BUSES = yaml_cfg.get("rs485_buses", [])               # dwie magistrale
CONTROL = yaml_cfg.get("control", {})                       # progi, czasy itp.
CONTROL.setdefault("temp_diff_percent", 5.0)
SECURITY = yaml_cfg.get("security", {})                     # polityka WAN/LAN
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

