from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

import backend.core.notifications as notifications
from backend.core.db import Base
from backend.core.notifications import (
    DEFAULT_PREFERENCES,
    get_notification_preferences,
    list_notifications,
    log_event,
    set_notification_preferences,
)


def setup_notifications_db(tmp_path, monkeypatch):
    engine = create_engine(
        f"sqlite:///{tmp_path / 'notifications.db'}",
        connect_args={"check_same_thread": False},
    )
    SessionLocal = sessionmaker(bind=engine)
    Base.metadata.create_all(bind=engine)
    monkeypatch.setattr(notifications, "SessionLocal", SessionLocal)
    return SessionLocal


def test_preferences_roundtrip(monkeypatch, tmp_path):
    setup_notifications_db(tmp_path, monkeypatch)
    updated = set_notification_preferences({"network": False, "mode": True, "extra": True})
    assert updated["network"] is False
    assert updated["mode"] is True
    assert updated["wind"] is True  # default preserved
    restored = get_notification_preferences()
    assert restored == updated
    # defaults stay untouched
    assert DEFAULT_PREFERENCES["network"] is True


def test_list_notifications_filters_categories(monkeypatch, tmp_path):
    setup_notifications_db(tmp_path, monkeypatch)
    log_event("MODE_CHANGE", meta={"mode": "manual"})
    log_event("WIND_LOCK_ON", meta={"group": "G1"}, category="wind")
    all_events = list_notifications(limit=10)
    assert len(all_events) == 2
    categories = {event["category"] for event in all_events}
    assert categories == {"mode", "wind"}
    mode_only = list_notifications(limit=10, categories=["mode"])
    assert len(mode_only) == 1
    assert mode_only[0]["event"] == "MODE_CHANGE"

