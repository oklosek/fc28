# -*- coding: utf-8 -*-
# backend/core/models.py – modele runtime (w pamięci) + odczyty uśredniane
from dataclasses import dataclass, field
from collections import deque
from typing import Deque

@dataclass
class SensorAverager:
    window: int = 5
    q: Deque[float] = field(default_factory=lambda: deque(maxlen=5))
    def add(self, v: float):
        self.q.append(float(v))
    def avg(self) -> float:
        if not self.q: return 0.0
        return sum(self.q) / len(self.q)

    # pozwala dynamicznie zmienić okno uśredniania
    def set_window(self, window: int):
        window = max(1, int(window))
        self.window = window
        # przycięcie istniejących próbek do nowego rozmiaru
        self.q = deque(list(self.q)[-window:], maxlen=window)

@dataclass
class SensorSnapshot:
    internal_temp: SensorAverager = field(default_factory=SensorAverager)
    external_temp: SensorAverager = field(default_factory=SensorAverager)
    internal_hum:  SensorAverager = field(default_factory=SensorAverager)
    wind_speed:    SensorAverager = field(default_factory=SensorAverager)
    rain:          SensorAverager = field(default_factory=SensorAverager)

    def set_window(self, window):
        """Ustaw okno uśredniania.

        Może przyjąć liczbę (dla wszystkich czujników) lub mapę {nazwa: okno}.
        """
        if isinstance(window, dict):
            for name, w in window.items():
                if hasattr(self, name):
                    getattr(self, name).set_window(w)
        else:
            for name in self.__dataclass_fields__:
                getattr(self, name).set_window(window)
