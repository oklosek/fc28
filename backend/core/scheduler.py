# -*- coding: utf-8 -*-
# backend/core/scheduler.py – kalibracja dzienna i przewietrzanie
import threading, time
from datetime import datetime
from backend.core.config import CONTROL

class Scheduler:
    def __init__(self, controller):
        self.controller = controller
        self._running = False
        self._t = None

    def start(self):
        self._running = True
        self._t = threading.Thread(target=self._loop, daemon=True)
        self._t.start()

    def stop(self):
        self._running = False

    def _loop(self):
        prev_flush_day = None
        prev_cal_day = None
        while self._running:
            now = datetime.now()
            # Przewietrzanie
            if now.hour == CONTROL.get("flush_hour", 12) and now.minute == 0:
                if prev_flush_day != now.date():
                    self.controller.manual_set_all(100.0)
                    prev_flush_day = now.date()
            # Kalibracja (zamykanie do 0%)
            if now.hour == CONTROL.get("calibration_hour", 0) and now.minute == 0:
                if prev_cal_day != now.date():
                    self.controller.calibrate_all()
                    prev_cal_day = now.date()
            time.sleep(1)
