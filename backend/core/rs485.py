# -*- coding: utf-8 -*-
# backend/core/rs485.py – odczyt z dwóch magistral RS485 (np. Modbus RTU) + uśrednianie
import asyncio
import logging
import time
import minimalmodbus
from backend.core.config import RS485_BUSES
from backend.core.models import SensorSnapshot

"""Odczyt danych z magistrali RS485.

W praktycznym zastosowaniu wykorzystywana jest biblioteka ``minimalmodbus`` do
komunikacji z urządzeniami Modbus RTU. W pliku ``settings.yaml`` znajdują się
informacje o dostępnych magistralach oraz rejestrach poszczególnych czujników.

Każdy obiekt :class:`RS485Bus` odpowiada jednej magistrali i przechowuje listę
czujników do odczytu. Metoda :meth:`RS485Bus.read_all` iteruje po tej liście,
otwierając port szeregowy dla każdego czujnika i próbując odczytać wskazany
rejestr. W przypadku błędów komunikacyjnych zwracana jest ``None``.
"""

class RS485Bus:
    def __init__(self, name, port, baudrate, sensors):
        self.name = name
        self.port = port
        self.baudrate = baudrate
        self.sensors = sensors  # lista czujników na tej magistrali
        self.errors = 0
        self.available = True
        self.next_retry = 0.0

    async def read_all(self) -> dict:
        """Odczytaj wszystkie zdefiniowane czujniki.

        Dla każdego czujnika tworzony jest obiekt :class:`minimalmodbus.Instrument`
        i wykonywany jest odczyt z podanego rejestru. Wynik konwertowany jest na
        ``float``. W przypadku wystąpienia błędów komunikacyjnych zwracana jest
        ``None``.
        """

        result = {}

        for s in self.sensors:
            map_key = s["map_to"]
            try:
                instrument = minimalmodbus.Instrument(self.port, s["slave"])
                instrument.serial.baudrate = self.baudrate
                instrument.mode = minimalmodbus.MODE_RTU
                # odczyt rejestru i konwersja na float
                value = float(instrument.read_register(s["reg"], 1))
                value = value * s.get("scale", 1) + s.get("offset", 0)
                result[map_key] = value
            except (minimalmodbus.ModbusException, OSError):
                # błędy komunikacji: timeouty, CRC itp.
                result[map_key] = None

        return result

class RS485Manager:
    def __init__(self):
        self.buses = [RS485Bus(**b) for b in RS485_BUSES]
        self.snapshot = SensorSnapshot()
        self._task = None
        self.running = False

        # konfiguracja obsługi błędów magistrali
        self.RETRY_DELAY = 0.5
        self.MAX_ERRORS = 3
        self.REINIT_INTERVAL = 30.0

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
                    if time.monotonic() < bus.next_retry:
                        continue
                    bus.available = True
                    bus.errors = 0
                try:
                    vals = await self._read_with_retry(bus)
                except Exception:
                    bus.errors += 1
                    if bus.errors >= self.MAX_ERRORS:
                        bus.available = False
                        bus.next_retry = time.monotonic() + self.REINIT_INTERVAL
                    continue
                else:
                    bus.errors = 0
                    for k, v in vals.items():
                        if v is not None:
                            getattr(self.snapshot, k).add(v)
            await asyncio.sleep(1.0)

    async def _read_with_retry(self, bus):
        try:
            return await bus.read_all()
        except Exception as e:
            logging.warning("RS485 bus %s read error: %s", bus.name, e)
            await asyncio.sleep(self.RETRY_DELAY)
            try:
                return await bus.read_all()
            except Exception as e:
                logging.warning("RS485 bus %s retry error: %s", bus.name, e)
                raise

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
