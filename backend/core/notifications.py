# -*- coding: utf-8 -*-
"""Notification utilities for recording and retrieving user-facing events."""
from __future__ import annotations

from typing import Dict, Iterable, List, Optional

from backend.core.db import EventLog, SessionLocal, Setting

DEFAULT_PREFERENCES: Dict[str, bool] = {
    "network": True,
    "mode": True,
    "wind": True,
    "updates": True,
    "environment": True,
    "system": True,
}

EVENT_CATEGORIES: Dict[str, str] = {
    "NETWORK_OFFLINE": "network",
    "NETWORK_ONLINE": "network",
    "SERVER_UNREACHABLE": "network",
    "MODE_CHANGE": "mode",
    "MANUAL_ACTION": "mode",
    "WIND_LOCK_ON": "wind",
    "WIND_LOCK_OFF": "wind",
    "UPDATE_AVAILABLE": "updates",
    "UPDATE_APPLIED": "updates",
    "UPDATE_FAILED": "updates",
    "UPDATE_UP_TO_DATE": "updates",
    "CO2_HIGH": "environment",
    "CO2_NORMAL": "environment",
    "HEATING_ON": "environment",
    "HEATING_OFF": "environment",
}


def _resolve_category(event: str, category: Optional[str]) -> str:
    if category:
        return category
    return EVENT_CATEGORIES.get(event, "system")


def log_event(event: str, *, level: str = "INFO", meta: Optional[Dict[str, object]] = None,
              category: Optional[str] = None) -> None:
    """Persist a notification event to the database."""
    resolved = _resolve_category(event, category)
    payload = dict(meta or {})
    payload.setdefault("category", resolved)
    try:
        with SessionLocal() as session:
            session.add(EventLog(level=level, event=event, meta=payload))
            session.commit()
    except Exception:
        # Notifications should not break business logic
        return


def list_notifications(limit: int = 50, categories: Optional[Iterable[str]] = None) -> List[Dict[str, object]]:
    """Return recent notification events limited to selected categories."""
    selected = {c for c in categories} if categories else None
    with SessionLocal() as session:
        query = session.query(EventLog).order_by(EventLog.ts.desc()).limit(limit)
        rows = list(query)
    events: List[Dict[str, object]] = []
    for row in rows:
        category = None
        if isinstance(row.meta, dict):
            category = row.meta.get("category")
        if not category:
            category = _resolve_category(row.event, None)
        if selected and category not in selected:
            continue
        events.append({
            "id": row.id,
            "timestamp": row.ts.isoformat() if row.ts else None,
            "level": row.level,
            "event": row.event,
            "meta": row.meta or {},
            "category": category,
        })
    return events


def get_notification_preferences() -> Dict[str, bool]:
    try:
        with SessionLocal() as session:
            row = session.get(Setting, "notifications.preferences")
            if not row or not row.value:
                return dict(DEFAULT_PREFERENCES)
            stored = row.value
            if isinstance(stored, dict):
                base = dict(DEFAULT_PREFERENCES)
                base.update({k: bool(v) for k, v in stored.items()})
                return base
    except Exception:
        pass
    return dict(DEFAULT_PREFERENCES)


def set_notification_preferences(prefs: Dict[str, bool]) -> Dict[str, bool]:
    merged = dict(DEFAULT_PREFERENCES)
    merged.update({k: bool(v) for k, v in prefs.items() if k in merged})
    try:
        with SessionLocal() as session:
            session.merge(Setting(key="notifications.preferences", value=merged))
            session.commit()
    except Exception:
        pass
    return merged


__all__ = [
    "log_event",
    "list_notifications",
    "get_notification_preferences",
    "set_notification_preferences",
    "DEFAULT_PREFERENCES",
]
