import sys
from pathlib import Path

sys.path.append(str(Path(__file__).resolve().parents[1]))

import time

from backend.core.config import CONTROL
from backend.core import controller as controller_module
from backend.core.scheduler import Scheduler
from backend.core.vents import Vent


def test_controller_loop_sleep(monkeypatch):
    monkeypatch.setitem(CONTROL, "controller_loop_s", 0.2)

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
            return {}

    c = controller_module.Controller(DummyRS485())
    durations = {}
    def fake_sleep(d):
        durations["dur"] = d
        c._running = False
    monkeypatch.setattr(time, "sleep", fake_sleep)

    c._running = True
    c._loop()
    c._async_loop.close()
    assert durations["dur"] == CONTROL["controller_loop_s"]


def test_scheduler_loop_sleep(monkeypatch):
    monkeypatch.setitem(CONTROL, "scheduler_loop_s", 0.3)
    monkeypatch.setitem(CONTROL, "flush_hour", 99)
    monkeypatch.setitem(CONTROL, "calibration_hour", 99)

    class DummyController:
        def manual_set_all(self, pct):
            pass
        def calibrate_all(self):
            pass

    s = Scheduler(DummyController())
    durations = {}
    def fake_sleep(d):
        durations["dur"] = d
        s._running = False
    monkeypatch.setattr(time, "sleep", fake_sleep)

    s._running = True
    s._loop()
    assert durations["dur"] == CONTROL["scheduler_loop_s"]
