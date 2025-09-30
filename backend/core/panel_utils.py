# -*- coding: utf-8 -*-
"""Utilities for building data structures consumed by installer panels."""
from __future__ import annotations

from typing import Any, Dict, List, Optional

try:
    import psutil  # type: ignore
except Exception:  # pragma: no cover - psutil is optional at runtime
    psutil = None

from backend.core.config import CONTROL, NETWORK_INTERFACES, BONEIOS
from backend.core.controller import Controller
from backend.core.test_mode import get_test_state


def build_sensor_overview(controller: Controller) -> Dict[str, Any]:
    env = controller.export_environment_snapshot()
    sensors: Dict[str, Dict[str, Any]] = {}
    for name, value in env["sensors"].items():
        sensors[name] = {
            "value": value,
            "unit": _sensor_unit(name),
            "source": env["sources"].get(name, "mqtt"),
        }
    if "wind_direction" not in sensors:
        sensors["wind_direction"] = {
            "value": env["sensors"].get("wind_direction"),
            "unit": "deg",
            "source": env["sources"].get("wind_direction", "mqtt"),
        }
    return {
        "metrics": sensors,
        "loops": {
            "controller": CONTROL.get("controller_loop_s", 1.0),
            "scheduler": CONTROL.get("scheduler_loop_s", 1.0),
        },
        "rs485": controller.export_rs485_status(),
        "network": _network_status(),
    }


def build_boneio_status(controller: Controller) -> Dict[str, Any]:
    devices: Dict[str, Dict[str, Any]] = {}
    meta = {entry.get("id"): entry for entry in BONEIOS}
    for vent in controller.vents.values():
        metadata = meta.get(vent.boneio_device, {})
        info = devices.setdefault(
            vent.boneio_device,
            {
                "device": vent.boneio_device,
                "base_topic": metadata.get("base_topic"),
                "description": metadata.get("description"),
                "vents": [],
                "all_available": True,
            },
        )
        info["vents"].append({
            "id": vent.id,
            "name": vent.name,
            "available": vent.available,
        })
        if not vent.available:
            info["all_available"] = False
    return {"devices": list(devices.values())}



def build_vent_status(controller: Controller) -> List[Dict[str, Any]]:
    return [
        {
            "id": vent.id,
            "name": vent.name,
            "position": vent.position,
            "target": getattr(vent, "user_target", None),
            "available": vent.available,
            "boneio_device": vent.boneio_device,
        }
        for vent in controller.vents.values()
    ]


def build_test_overview(controller: Controller) -> Dict[str, Any]:
    state = get_test_state()
    return {
        "test_mode": {
            "enabled": state["enabled"],
            "overrides": state["overrides"],
            "manual_history": state.get("manual_history", []),
            "override_history": state.get("override_history", []),
            "metadata": state.get("metadata", {}),
            "updated_at": state["updated_at"],
        },
        "boneio": build_boneio_status(controller)["devices"],
        "vents": build_vent_status(controller),
    }


def _network_status() -> List[Dict[str, Any]]:
    mapping = _resolve_network_mapping()
    raw_specs = {
        role: (NETWORK_INTERFACES.get(role) or {})
        for role in ("lan", "wan")
    }

    if psutil is None:  # pragma: no cover - fallback when psutil is missing
        return [
            {
                "role": role,
                "name": mapping.get(role),
                "is_up": None,
                "addresses": [],
                "error": "psutil_not_available",
                "config": {k: v for k, v in raw_specs.get(role, {}).items() if k != "name"},
            }
            for role in ("lan", "wan")
        ]

    stats = psutil.net_if_stats()
    addrs = psutil.net_if_addrs()
    assigned: set[str] = set()
    results: List[Dict[str, Any]] = []

    for role in ("lan", "wan"):
        configured_name = mapping.get(role)
        name = configured_name or _select_interface(stats.keys(), assigned)
        entry = _build_interface_entry(
            role=role,
            name=name,
            stats=stats,
            addrs=addrs,
            config_spec=raw_specs.get(role) or {},
        )
        if name:
            assigned.add(name)
        results.append(entry)

    return results


def _resolve_network_mapping() -> Dict[str, Optional[str]]:
    mapping: Dict[str, Optional[str]] = {}
    if isinstance(NETWORK_INTERFACES, dict):
        for role in ("lan", "wan"):
            value = NETWORK_INTERFACES.get(role)
            if isinstance(value, dict):
                name = value.get("interface") or value.get("name")
            elif isinstance(value, str):
                name = value.strip()
            else:
                name = None
            mapping[role] = name or None
    else:
        mapping = {"lan": None, "wan": None}
    return mapping


def _select_interface(candidates: Any, excluded: set[str]) -> Optional[str]:
    names = [str(name) for name in candidates]
    names.sort()
    for name in names:
        lowered = name.lower()
        if lowered.startswith("lo") or "loopback" in lowered:
            continue
        if name in excluded:
            continue
        return name
    return None


def _build_interface_entry(
    *,
    role: str,
    name: Optional[str],
    stats: Any,
    addrs: Any,
    config_spec: Dict[str, Any],
) -> Dict[str, Any]:
    entry: Dict[str, Any] = {
        "role": role,
        "name": name,
        "addresses": [],
        "config": {k: v for k, v in config_spec.items() if k != "name"},
    }
    if not name:
        entry["is_up"] = None
        entry["error"] = "interface_not_configured"
        return entry

    if name not in stats:
        entry["is_up"] = False
        entry["error"] = "interface_not_found"
        return entry

    iface_stats = stats[name]
    entry["is_up"] = bool(getattr(iface_stats, "isup", False))
    speed = getattr(iface_stats, "speed", 0)
    entry["speed_mbps"] = speed if isinstance(speed, (int, float)) and speed > 0 else None
    entry["mtu"] = getattr(iface_stats, "mtu", None)

    addresses: List[str] = []
    mac: Optional[str] = None
    for item in addrs.get(name, []):
        family = getattr(item.family, "name", str(item.family))
        address = getattr(item, "address", None)
        if not address:
            continue
        if family in ("AF_LINK", "AF_PACKET"):
            mac = address
            continue
        if "AF_INET" in family:
            formatted = address
            netmask = getattr(item, "netmask", None)
            if netmask:
                formatted = f"{formatted}/{netmask}"
            addresses.append(formatted)
        elif "AF_INET6" in family:
            formatted = address.split("%", 1)[0]
            addresses.append(formatted)
    entry["addresses"] = addresses
    entry["mac"] = mac
    if not addresses and not mac:
        entry.setdefault("error", "no_addresses")
    return entry


def _sensor_unit(name: str) -> Optional[str]:
    mapping = {
        "internal_temp": "degC",
        "external_temp": "degC",
        "internal_hum": "%",
        "external_hum": "%",
        "internal_co2": "ppm",
        "wind_speed": "m/s",
        "wind_gust": "m/s",
        "rain": "mm",
    }
    return mapping.get(name)


__all__ = [
    "build_sensor_overview",
    "build_boneio_status",
    "build_vent_status",
    "build_test_overview",
]
