# -*- coding: utf-8 -*-
# backend/core/rs485.py - odczyt z magistral RS485 (np. Modbus RTU) + u�rednianie
from __future__ import annotations

import asyncio
import logging
import time
from typing import Callable, Dict, List

import minimalmodbus

from backend.core.config import RS485_BUSES, AVG_WINDOW_S, SENSORS
from backend.core.models import SensorSnapshot
from backend.core.rs485_drivers import DRIVER_REGISTRY, SensorDriver


class SimpleRegisterSensor:
    """Minimalny odczyt pojedynczego rejestru Modbus."""

    def __init__(self, cfg: dict):
        self.slave = int(cfg["slave"])
        self.register = int(cfg["reg"])
        self.map_to = cfg.get("map_to")
        self.scale = float(cfg.get("scale", 1.0))
        self.offset = float(cfg.get("offset", 0.0))
        self.decimals = int(cfg.get("decimals", 1))
        self.function = int(cfg.get("function", 3))
        self.signed = bool(cfg.get("signed", False))

    def read(self, instrument_factory: Callable[[int], minimalmodbus.Instrument]) -> Dict[str, float]:
        if not self.map_to:
            return {}
        instrument = instrument_factory(self.slave)
        value = instrument.read_register(
            self.register,
            self.decimals,
            functioncode=self.function,
            signed=self.signed,
        )
        return {self.map_to: float(value) * self.scale + self.offset}

    def outputs(self) -> List[str]:
        return [self.map_to] if self.map_to else []


class RS485Bus:
    def __init__(self, name, port, baudrate, sensors, timeout=0.2, **serial_kwargs):
        self.name = name
        self.port = port
        self.baudrate = baudrate
        self.timeout = timeout
        allowed_serial_keys = {"bytesize", "parity", "stopbits"}
        self.serial_kwargs = {k: serial_kwargs.get(k) for k in allowed_serial_keys}
        self.handlers: List[SensorDriver | SimpleRegisterSensor] = []
        for item in sensors:
            driver_name = item.get("driver")
            if driver_name:
                driver_cls = DRIVER_REGISTRY.get(driver_name)
                if not driver_cls:
                    logging.warning("Unknown RS485 driver '%s' on bus %s", driver_name, name)
                    continue
                try:
                    handler = driver_cls(item)
                except Exception as exc:  # pragma: no cover - konfiguracja
                    logging.warning("Failed to initialise driver '%s' on %s: %s", driver_name, name, exc)
                    continue
                self.handlers.append(handler)
            else:
                try:
                    handler = SimpleRegisterSensor(item)
                except KeyError as exc:  # pragma: no cover - b��dna konfiguracja
                    logging.warning("RS485 sensor config missing %s on bus %s", exc, name)
                    continue
                self.handlers.append(handler)
        self.errors = 0
        self.available = True
        self.next_retry = 0.0

    def _instrument_factory(self, slave: int) -> minimalmodbus.Instrument:
        instrument = minimalmodbus.Instrument(self.port, slave)
        instrument.serial.baudrate = self.baudrate
        instrument.serial.timeout = self.timeout
        if self.serial_kwargs.get("bytesize") is not None:
            instrument.serial.bytesize = self.serial_kwargs["bytesize"]
        if self.serial_kwargs.get("parity") is not None:
            instrument.serial.parity = self.serial_kwargs["parity"]
        if self.serial_kwargs.get("stopbits") is not None:
            instrument.serial.stopbits = self.serial_kwargs["stopbits"]
        instrument.mode = minimalmodbus.MODE_RTU
        instrument.clear_buffers_before_each_transaction = True
        return instrument

    def _expected_keys(self, handler: SensorDriver | SimpleRegisterSensor) -> List[str]:
        if isinstance(handler, SimpleRegisterSensor):
            return handler.outputs()
        if isinstance(handler, SensorDriver):
            return [v for v in handler.outputs.values() if v]
        return []

    async def read_all(self) -> Dict[str, float | None]:
        result: Dict[str, float | None] = {}
        for handler in self.handlers:
            try:
                values = await asyncio.to_thread(handler.read, self._instrument_factory)
            except (minimalmodbus.ModbusException, OSError) as exc:
                logging.warning("RS485 sensor read error on %s: %s", self.name, exc)
                for key in self._expected_keys(handler):
                    result[key] = None
            except Exception as exc:  # pragma: no cover - nieoczekiwane b��dy sterownika
                logging.warning("Unexpected RS485 sensor error on %s: %s", self.name, exc)
                for key in self._expected_keys(handler):
                    result[key] = None
            else:
                for key, value in values.items():
                    result[key] = value
        return result


class RS485Manager:
    def __init__(self):
        self.buses = [RS485Bus(**b) for b in RS485_BUSES]
        self.snapshot = SensorSnapshot()
        self.snapshot.set_window(AVG_WINDOW_S)
        per_windows = {}
        for name, cfg in SENSORS.items():
            if not isinstance(cfg, dict):
                continue
            window = cfg.get("avg_window_s")
            if window is None:
                continue
            try:
                per_windows[name] = int(window)
            except (TypeError, ValueError):
                continue
        if per_windows:
            self.snapshot.set_windows(per_windows)
        self._task = None
        self.running = False

        # konfiguracja obs�ugi b��d�w magistrali
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
                    for key, value in vals.items():
                        if value is None:
                            continue
                        if hasattr(self.snapshot, key):
                            getattr(self.snapshot, key).add(value)
                        else:
                            logging.debug("Ignoring RS485 value for unknown sensor '%s'", key)
            await asyncio.sleep(1.0)

    async def _read_with_retry(self, bus: RS485Bus):
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

    def averages(self) -> Dict[str, float | None]:
        return self.snapshot.averages()
