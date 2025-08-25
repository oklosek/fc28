# -*- coding: utf-8 -*-
# backend/core/rs485.py – odczyt z dwóch magistral RS485 (np. Modbus RTU) + uśrednianie
import asyncio
import logging
import time
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
        self.error_count = 0
        self.available = True
        self.next_init = 0.0

    async def init_port(self):
        """Ponowna inicjalizacja portu."""
        # W realnej implementacji tu otwierasz port szeregowy.
        self.available = True
        self.error_count = 0
        self.next_init = 0.0

    async def read_all(self) -> dict:
        # TODO: zastąp poniższy mock prawdziwymi odczytami RTU
        # np. minimalmodbus.Instrument('/dev/ttyS0', slave_id).read_register(reg, 1)
        # Zwróć dict { "internal_temp": 23.4, ... } dla dopiętych czujników
        result = {}
        for s in self.sensors:
            result[s["map_to"]] = 0.0  # domyślnie
        return result

class RS485Manager:
    def __init__(self):
        self.buses = [RS485Bus(**b) for b in RS485_BUSES]
        self.snapshot = SensorSnapshot()
        self._task = None
        self.running = False
        self.max_errors = 3
        self.retry_delay = 0.5
        self.reinit_delay = 30.0

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
                if not bus.available:
                    if time.monotonic() >= bus.next_init:
                        try:
                            await bus.init_port()
                        except Exception as exc:
                            logging.warning("RS485 %s reinit failed: %s", bus.name, exc)
                            bus.next_init = time.monotonic() + self.reinit_delay
                        continue
                    else:
                        continue
                try:
                    vals = await bus.read_all()
                except Exception as exc:
                    logging.warning("RS485 %s read error: %s", bus.name, exc)
                    bus.error_count += 1
                    await asyncio.sleep(self.retry_delay)
                    try:
                        vals = await bus.read_all()
                    except Exception as exc2:
                        logging.warning("RS485 %s retry failed: %s", bus.name, exc2)
                        bus.error_count += 1
                        if bus.error_count >= self.max_errors:
                            bus.available = False
                            bus.next_init = time.monotonic() + self.reinit_delay
                        continue
                else:
                    bus.error_count = 0
                for k, v in vals.items():
                    getattr(self.snapshot, k).add(v)
            await asyncio.sleep(1.0)

    def averages(self) -> dict:
        return {
            "internal_temp": self.snapshot.internal_temp.avg(),
            "external_temp": self.snapshot.external_temp.avg(),
            "internal_hum":  self.snapshot.internal_hum.avg(),
            "wind_speed":    self.snapshot.wind_speed.avg(),
            "rain":          self.snapshot.rain.avg(),
        }
