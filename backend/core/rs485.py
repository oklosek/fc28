# -*- coding: utf-8 -*-
# backend/core/rs485.py – odczyt z dwóch magistral RS485 (np. Modbus RTU) + uśrednianie
import asyncio
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
rejestr. W przypadku błędów komunikacyjnych zwracana jest ostatnia poprawna
wartość (jeśli dostępna) lub ``None``.
"""

class RS485Bus:
    def __init__(self, name, port, baudrate, sensors):
        self.name = name
        self.port = port
        self.baudrate = baudrate
        self.sensors = sensors  # lista czujników na tej magistrali
        # przechowywanie ostatnich poprawnych wartości poszczególnych czujników
        self._last_values: dict[str, float] = {}

    async def read_all(self) -> dict:
        """Odczytaj wszystkie zdefiniowane czujniki.

        Dla każdego czujnika tworzony jest obiekt :class:`minimalmodbus.Instrument`
        i wykonywany jest odczyt z podanego rejestru. Wynik konwertowany jest na
        ``float``. W przypadku wystąpienia błędów komunikacyjnych zwracana jest
        ostatnia poprawna wartość (jeśli istnieje) lub ``None``.
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
                self._last_values[map_key] = value
                result[map_key] = value
            except (minimalmodbus.ModbusException, OSError):
                # błędy komunikacji: timeouty, CRC itp.
                result[map_key] = self._last_values.get(map_key)

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
