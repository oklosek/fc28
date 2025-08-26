import sys
from pathlib import Path

sys.path.append(str(Path(__file__).resolve().parents[1]))
from backend.core import controller as controller_module
from backend.core.mqtt_client import sensor_bus
from backend.core.vents import Vent


def test_zero_values_from_rs485_override_sensor_bus(monkeypatch):
    """RS485 readings equal to zero should replace MQTT values in s1."""

    # dummy DB session to avoid real database interactions
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

    # prepare sensor_bus with a non-zero value
    sensor_bus.internal_temp.q.clear()
    sensor_bus.internal_temp.add(5.0)

    class DummyRS485:
        def averages(self):
            return {
                "internal_temp": 0.0,
                "external_temp": None,
                "internal_hum": None,
                "wind_speed": None,
                "rain": None,
            }

    controller = controller_module.Controller(DummyRS485())

    captured = {}

    def fake_compute_auto_target(self, s):
        captured["s1"] = s.copy()
        return 0.0

    monkeypatch.setattr(controller_module.Controller, "_compute_auto_target", fake_compute_auto_target)
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

    assert captured["s1"]["internal_temp"] == 0.0

