import sys
from pathlib import Path

sys.path.append(str(Path(__file__).resolve().parents[1]))

from backend.core.rs485 import RS485Manager
from backend.core import controller as controller_module
from backend.core.mqtt_client import sensor_bus
from backend.core.vents import Vent


def test_sensor_bus_averages_empty_returns_none():
    for name in ("internal_temp", "external_temp", "internal_hum", "wind_speed", "rain"):
        getattr(sensor_bus, name).q.clear()
    assert sensor_bus.averages() == {
        "internal_temp": None,
        "external_temp": None,
        "internal_hum": None,
        "wind_speed": None,
        "rain": None,
    }

def test_rs485_manager_averages_empty_returns_none():
    mgr = RS485Manager()
    assert mgr.averages() == {
        "internal_temp": None,
        "external_temp": None,
        "internal_hum": None,
        "wind_speed": None,
        "rain": None,
    }


def test_controller_skips_on_missing_readings(monkeypatch):
    for name in ("internal_temp", "external_temp", "internal_hum", "wind_speed", "rain"):
        getattr(sensor_bus, name).q.clear()

    class DummySession:
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

    monkeypatch.setattr(controller_module, "SessionLocal", lambda: DummySession())
    monkeypatch.setattr(controller_module.Controller, "_save_vent_state", lambda self, vid: None)

    async def noop_move_to(self, pct):
        self.position = pct
    monkeypatch.setattr(Vent, "move_to", noop_move_to)

    class DummyRS485:
        def averages(self):
            return {
                "internal_temp": None,
                "external_temp": None,
                "internal_hum": None,
                "wind_speed": None,
                "rain": None,
            }

    controller = controller_module.Controller(DummyRS485())

    calls = {"compute": 0}

    def fake_compute(self, s):
        calls["compute"] += 1
        return 0.0

    monkeypatch.setattr(controller_module.Controller, "_compute_auto_target", fake_compute)
    monkeypatch.setattr(controller_module.Controller, "_apply_safety", lambda self, base, s, manual: base)

    async def dummy_auto_move(self, target, critical):
        return None

    monkeypatch.setattr(controller_module.Controller, "_auto_move_to", dummy_auto_move)

    def fake_sleep(d):
        controller._running = False

    monkeypatch.setattr(controller_module.time, "sleep", fake_sleep)

    controller._running = True
    controller._loop()
    controller._async_loop.close()

    assert calls["compute"] == 0

def test_controller_resumes_when_readings_available(monkeypatch):
    values = {
        "internal_temp": 21.5,
        "external_temp": 18.0,
        "internal_hum": 55.0,
        "wind_speed": 3.5,
        "rain": 0.0,
    }
    for name, val in values.items():
        averager = getattr(sensor_bus, name)
        averager.q.clear()
        averager.add(val)

    class DummySession:
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

    monkeypatch.setattr(controller_module, "SessionLocal", lambda: DummySession())
    monkeypatch.setattr(controller_module.Controller, "_save_vent_state", lambda self, vid: None)

    async def noop_move_to(self, pct):
        self.position = pct

    monkeypatch.setattr(Vent, "move_to", noop_move_to)

    class DummyRS485:
        def averages(self):
            return {k: None for k in values}

    controller = controller_module.Controller(DummyRS485())

    calls = {"compute": 0, "auto": 0}

    def fake_compute(self, snapshot):
        calls["compute"] += 1
        assert snapshot == values
        return 25.0

    def fake_apply(self, base, snapshot, manual):
        assert manual is False
        return base

    async def fake_auto_move(self, target, critical):
        calls["auto"] += 1
        assert not critical
        assert target == 25.0

    monkeypatch.setattr(controller_module.Controller, "_compute_auto_target", fake_compute)
    monkeypatch.setattr(controller_module.Controller, "_apply_safety", fake_apply)
    monkeypatch.setattr(controller_module.Controller, "_auto_move_to", fake_auto_move)

    def fake_sleep(delay):
        controller._running = False

    monkeypatch.setattr(controller_module.time, "sleep", fake_sleep)

    controller._running = True
    controller._loop()
    controller._async_loop.close()

    assert calls["compute"] == 1
    assert calls["auto"] == 1

    for name in values:
        getattr(sensor_bus, name).q.clear()
