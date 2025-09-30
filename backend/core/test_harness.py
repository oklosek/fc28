# -*- coding: utf-8 -*-
"""In-memory harness for installer test panel simulations."""
from __future__ import annotations

import time
from collections import deque
from threading import Lock
from typing import Any, Deque, Dict, List, Optional


class TestHarness:
    """Keeps diagnostic state for test mode, simulations and manual overrides."""

    __slots__ = (
        "_enabled",
        "_sensor_overrides",
        "_manual_history",
        "_override_history",
        "_metadata",
        "_lock",
        "_updated_at",
    )

    def __init__(self, history_size: int = 100) -> None:
        self._enabled: bool = False
        self._sensor_overrides: Dict[str, float] = {}
        self._manual_history: Deque[Dict[str, Any]] = deque(maxlen=history_size)
        self._override_history: Deque[Dict[str, Any]] = deque(maxlen=history_size)
        self._metadata: Dict[str, Any] = {}
        self._lock = Lock()
        self._updated_at: Optional[float] = None

    # ------------------------------------------------------------------
    # Test mode toggles
    # ------------------------------------------------------------------
    def set_enabled(self, enabled: bool, *, reason: Optional[str] = None) -> Dict[str, Any]:
        with self._lock:
            self._enabled = bool(enabled)
            if not self._enabled:
                self._sensor_overrides.clear()
            self._updated_at = time.time()
            if reason:
                self._metadata["reason"] = reason
            return self._snapshot_locked()

    def is_enabled(self) -> bool:
        with self._lock:
            return self._enabled

    # ------------------------------------------------------------------
    # Sensor overrides
    # ------------------------------------------------------------------
    def set_sensor_overrides(self, values: Dict[str, Any]) -> Dict[str, Any]:
        cleaned: Dict[str, float] = {}
        for key, raw in values.items():
            try:
                cleaned[key] = float(raw)
            except (TypeError, ValueError):
                continue
        with self._lock:
            if cleaned:
                self._enabled = True
                self._sensor_overrides.update(cleaned)
                self._override_history.appendleft(
                    {
                        "ts": time.time(),
                        "values": dict(cleaned),
                    }
                )
            self._updated_at = time.time()
            return self._snapshot_locked()

    def clear_sensor_overrides(self) -> Dict[str, Any]:
        with self._lock:
            self._sensor_overrides.clear()
            self._override_history.appendleft({"ts": time.time(), "values": {}})
            self._updated_at = time.time()
            return self._snapshot_locked()

    def apply_overrides(self, sensor_data: Dict[str, Any]) -> Dict[str, Any]:
        with self._lock:
            if not self._enabled or not self._sensor_overrides:
                return sensor_data
            patched = dict(sensor_data)
            patched.update(self._sensor_overrides)
            return patched

    # ------------------------------------------------------------------
    # Manual action history
    # ------------------------------------------------------------------
    def record_manual_action(self, action: Dict[str, Any]) -> None:
        payload = dict(action)
        payload.setdefault("ts", time.time())
        with self._lock:
            self._manual_history.appendleft(payload)
            self._updated_at = time.time()

    # ------------------------------------------------------------------
    # Metadata helpers
    # ------------------------------------------------------------------
    def set_metadata(self, key: str, value: Any) -> None:
        with self._lock:
            self._metadata[key] = value
            self._updated_at = time.time()

    def get_metadata(self, key: str, default: Any = None) -> Any:
        with self._lock:
            return self._metadata.get(key, default)

    # ------------------------------------------------------------------
    # Export
    # ------------------------------------------------------------------
    def snapshot(self) -> Dict[str, Any]:
        with self._lock:
            return self._snapshot_locked()

    def _snapshot_locked(self) -> Dict[str, Any]:
        return {
            "enabled": self._enabled,
            "overrides": dict(self._sensor_overrides),
            "manual_history": list(self._manual_history),
            "override_history": list(self._override_history),
            "metadata": dict(self._metadata),
            "updated_at": self._updated_at,
        }


HARNESS = TestHarness()


__all__ = ["HARNESS", "TestHarness"]
