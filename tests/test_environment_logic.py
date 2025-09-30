import sys
from datetime import datetime, time
from pathlib import Path

import pytest

sys.path.append(str(Path(__file__).resolve().parents[1]))

from backend.core import controller as controller_module  # noqa: E402


class DummyRS485:
    def averages(self):
        return {}


class NoopSession:
    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc, tb):
        pass

    def get(self, *args, **kwargs):
        return None

    def add(self, *args, **kwargs):
        pass

    def merge(self, *args, **kwargs):
        pass

    def commit(self):
        pass

    def query(self, *args, **kwargs):
        return self

    def filter(self, *args, **kwargs):
        return self

    def all(self):
        return []


@pytest.fixture
def patched_controller(monkeypatch):
    monkeypatch.setattr(controller_module.Controller, "_load_state_from_db", lambda self: None)
    monkeypatch.setattr(controller_module.Controller, "_apply_control_overrides", lambda self: None)
    monkeypatch.setattr(controller_module.Controller, "_apply_plan_overrides", lambda self: None)
    monkeypatch.setattr(controller_module.Controller, "_apply_heating_overrides", lambda self: None)
    monkeypatch.setattr(controller_module, "SessionLocal", lambda: NoopSession())
    monkeypatch.setitem(controller_module.CONTROL, "target_temp_c", 22.0)
    monkeypatch.setitem(controller_module.CONTROL, "day_target_temp_c", 22.0)
    monkeypatch.setitem(controller_module.CONTROL, "night_target_temp_c", 22.0)
    monkeypatch.setitem(controller_module.CONTROL, "day_start", "06:00")
    monkeypatch.setitem(controller_module.CONTROL, "night_start", "20:00")
    monkeypatch.setitem(controller_module.CONTROL, "night_max_open_percent", 40.0)
    monkeypatch.setitem(controller_module.HEATING, "enabled", False)
    monkeypatch.setitem(controller_module.HEATING, "day_start", "06:00")
    monkeypatch.setitem(controller_module.HEATING, "night_start", "20:00")
    ctrl = controller_module.Controller(DummyRS485())
    return ctrl


def test_environment_day_night_target(monkeypatch, patched_controller):
    ctrl = patched_controller
    monkeypatch.setitem(controller_module.CONTROL, "day_target_temp_c", 24.0)
    monkeypatch.setitem(controller_module.CONTROL, "night_target_temp_c", 18.0)
    ctrl._refresh_schedules()
    day_now = datetime.combine(datetime.today(), time(10, 0))
    night_now = datetime.combine(datetime.today(), time(23, 0))
    assert ctrl._resolve_environment_target(day_now) == pytest.approx(24.0)
    assert ctrl._resolve_environment_target(night_now) == pytest.approx(18.0)


def test_night_cap_when_heating_disabled(monkeypatch, patched_controller):
    ctrl = patched_controller
    monkeypatch.setitem(controller_module.CONTROL, "night_max_open_percent", 35.0)

    class NightDatetime:
        @staticmethod
        def now(tz=None):
            return datetime(2024, 1, 1, 22, 0)

    monkeypatch.setattr(controller_module, "datetime", NightDatetime)

    ctrl._refresh_schedules()
    sensors = {"wind_speed": 3.0, "rain": 0.0, "internal_hum": 50.0}
    limited = ctrl._apply_safety(80.0, sensors, manual=False)
    assert limited == pytest.approx(35.0)
    manual = ctrl._apply_safety(80.0, sensors, manual=True)
    assert manual == pytest.approx(80.0)
    monkeypatch.setitem(controller_module.HEATING, "enabled", True)
    ctrl._refresh_heating_schedule()
    unrestricted = ctrl._apply_safety(80.0, sensors, manual=False)
    assert unrestricted == pytest.approx(80.0)


def test_co2_logging(monkeypatch):
    events = []

    class EventSession(NoopSession):
        def add(self, obj):
            events.append((obj.event, obj.level))

    monkeypatch.setattr(controller_module.Controller, "_load_state_from_db", lambda self: None)
    monkeypatch.setattr(controller_module.Controller, "_apply_control_overrides", lambda self: None)
    monkeypatch.setattr(controller_module.Controller, "_apply_plan_overrides", lambda self: None)
    monkeypatch.setattr(controller_module.Controller, "_apply_heating_overrides", lambda self: None)
    monkeypatch.setattr(controller_module, "SessionLocal", lambda: EventSession())

    monkeypatch.setitem(controller_module.CONTROL, "target_temp_c", 22.0)
    monkeypatch.setitem(controller_module.CONTROL, "day_target_temp_c", 22.0)
    monkeypatch.setitem(controller_module.CONTROL, "night_target_temp_c", 22.0)
    monkeypatch.setitem(controller_module.CONTROL, "day_start", "06:00")
    monkeypatch.setitem(controller_module.CONTROL, "night_start", "20:00")
    monkeypatch.setitem(controller_module.CONTROL, "night_max_open_percent", 40.0)
    monkeypatch.setitem(controller_module.CONTROL, "co2_thr_ppm", 800.0)
    monkeypatch.setitem(controller_module.CONTROL, "min_open_co2_percent", 50.0)
    monkeypatch.setitem(controller_module.HEATING, "enabled", True)
    monkeypatch.setitem(controller_module.HEATING, "day_start", "06:00")
    monkeypatch.setitem(controller_module.HEATING, "night_start", "20:00")

    ctrl = controller_module.Controller(DummyRS485())

    sensors_high = {
        "internal_temp": 24.0,
        "external_temp": 10.0,
        "internal_hum": 40.0,
        "wind_speed": 2.0,
        "rain": 0.0,
        "internal_co2": 950.0,
    }
    sensors_low = dict(sensors_high)
    sensors_low["internal_co2"] = 500.0

    pct_high = ctrl._compute_auto_target(sensors_high)
    pct_low = ctrl._compute_auto_target(sensors_low)

    assert pct_high >= controller_module.CONTROL["min_open_co2_percent"]
    assert pct_low < pct_high
    assert ("CO2_HIGH", "WARN") in events
    assert ("CO2_NORMAL", "INFO") in events

