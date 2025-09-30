# -*- coding: utf-8 -*-
"""In-memory test mode helpers for diagnostics panel."""
from __future__ import annotations

from typing import Any, Dict, Iterable, Optional

from backend.core.test_harness import HARNESS


def get_test_state() -> Dict[str, Any]:
    state = HARNESS.snapshot()
    return {
        "enabled": state["enabled"],
        "overrides": state["overrides"],
        "manual_history": state["manual_history"],
        "override_history": state["override_history"],
        "metadata": state["metadata"],
        "updated_at": state["updated_at"],
    }


def set_test_mode(enabled: bool, *, reason: Optional[str] = None) -> Dict[str, Any]:
    return HARNESS.set_enabled(enabled, reason=reason)


def set_overrides(values: Dict[str, Any]) -> Dict[str, Any]:
    return HARNESS.set_sensor_overrides(values)


def clear_overrides() -> Dict[str, Any]:
    return HARNESS.clear_sensor_overrides()


def apply_overrides(sensor_data: Dict[str, Any]) -> Dict[str, Any]:
    return HARNESS.apply_overrides(sensor_data)


def record_manual_action(action: Dict[str, Any]) -> None:
    HARNESS.record_manual_action(action)


def set_metadata(key: str, value: Any) -> None:
    HARNESS.set_metadata(key, value)


def get_metadata(key: str, default: Any = None) -> Any:
    return HARNESS.get_metadata(key, default)


def mark_manual_success(targets: Iterable[str], value: float) -> None:
    HARNESS.record_manual_action(
        {
            "type": "manual",
            "targets": list(targets),
            "value": float(value),
        }
    )


__all__ = [
    "get_test_state",
    "set_test_mode",
    "set_overrides",
    "clear_overrides",
    "apply_overrides",
    "record_manual_action",
    "set_metadata",
    "get_metadata",
    "mark_manual_success",
]
