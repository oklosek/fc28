# -*- coding: utf-8 -*-
# backend/core/rs485.py – odczyt z dwóch magistral RS485 (np. Modbus RTU) + uśrednianie
import asyncio
from backend.core.config import RS485_BUSES
from backend.core.models import SensorSnapshot

# Uwaga: w realu użyj minimalmodbus/pymodbus; tu pokazuję szkic z pseudo-odczytem
# aby kod działał nawet bez sprzętu. W settings.yaml wskazujesz porty i rejestry.

class RS485Bus:
    def __init__(self, name, port, baudrate, sensors):
        self.name = name
        self.port = port
        self.baudrate = baudrate
        self.sensors = sensors  # lista czujników na tej magistrali
    async def read_all(self) -> dict:
        # TODO: zastąp poniższy mock prawdziwymi odczytami RTU
        # np. minimalmodbus.Instrument('/dev/ttyS0', slave_id).read_register(reg, 1)
        # Zwróć dict { "internal_temp": 23.4, ... } dla dopiętych czujników
        result = {}
        for s in self.sensors:
            # zwróć None przy nieudanym odczycie aby odróżnić od wartości 0
            result[s["map_to"]] = None
        return result

class RS485Manager:
    def __init__(self):
        self.buses = [RS485Bus(**b) for b in RS485_BUSES]
        self.snapshot = SensorSnapshot()
        self._task = None
        self.running = False

    async def start(self):
        self.running = True
        self._task = asyncio.create_task(self._loop())

    async def stop(self):
        self.running = False
        if self._task:
            try:
                await self._task
            except asyncio.CancelledError:
                pass
            finally:
                self._task = None

    async def _loop(self):
        while self.running:
            # zbierz odczyty z obu magistral i uśrednij
            for bus in self.buses:
                vals = await bus.read_all()
                for k, v in vals.items():
                    if v is not None:
                        getattr(self.snapshot, k).add(v)
            await asyncio.sleep(1.0)

    def averages(self) -> dict:
        def _avg_or_none(av):
            return av.avg() if av.q else None

        return {
            "internal_temp": _avg_or_none(self.snapshot.internal_temp),
            "external_temp": _avg_or_none(self.snapshot.external_temp),
            "internal_hum":  _avg_or_none(self.snapshot.internal_hum),
            "wind_speed":    _avg_or_none(self.snapshot.wind_speed),
            "rain":          _avg_or_none(self.snapshot.rain),
        }
