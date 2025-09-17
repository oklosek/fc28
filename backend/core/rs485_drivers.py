# -*- coding: utf-8 -*-
"""Specialized RS485 sensor drivers for SenseCAP devices."""

from __future__ import annotations

from typing import Callable, Dict, Optional, Sequence

import minimalmodbus

InstrumentFactory = Callable[[int], minimalmodbus.Instrument]


def _combine_words(high: int, low: int) -> int:
    return ((high & 0xFFFF) << 16) | (low & 0xFFFF)


def _convert_signed(value: int) -> int:
    if value & 0x80000000:
        return value - 0x100000000
    return value


class SensorDriver:
    """Base class for RS485 sensor drivers."""

    DEFAULT_OUTPUTS: Dict[str, Optional[str]] = {}

    def __init__(self, cfg: dict):
        if "slave" not in cfg:
            raise ValueError("Missing slave address in RS485 sensor config")
        self.slave: int = int(cfg["slave"])
        outputs_cfg = cfg.get("outputs", {}) or {}
        mapping: Dict[str, str] = {}
        for logical, default in self.DEFAULT_OUTPUTS.items():
            target = outputs_cfg.get(logical, default)
            if target:
                mapping[logical] = str(target)
        self.outputs = mapping
        self.cfg = cfg

    def read(self, instrument_factory: InstrumentFactory) -> Dict[str, float]:  # pragma: no cover - interface hook
        raise NotImplementedError


class SensecapSCO203BDriver(SensorDriver):
    """Driver for the SenseCAP S-CO2-03B indoor sensor."""

    DEFAULT_OUTPUTS = {
        "co2": "internal_co2",
        "temperature": "internal_temp",
        "humidity": "internal_hum",
    }

    def __init__(self, cfg: dict):
        super().__init__(cfg)
        self.function = int(cfg.get("function", 3))

    def read(self, instrument_factory: InstrumentFactory) -> Dict[str, float]:
        instrument = instrument_factory(self.slave)
        co2 = instrument.read_register(0, 0, functioncode=self.function, signed=False)
        temp_raw = instrument.read_register(1, 0, functioncode=self.function, signed=True)
        hum_raw = instrument.read_register(2, 0, functioncode=self.function, signed=False)
        data: Dict[str, float] = {}
        if "co2" in self.outputs:
            data[self.outputs["co2"]] = float(co2)
        if "temperature" in self.outputs:
            data[self.outputs["temperature"]] = temp_raw / 100.0
        if "humidity" in self.outputs:
            data[self.outputs["humidity"]] = hum_raw / 100.0
        return data


class SensecapS500V2Driver(SensorDriver):
    """Driver for the SenseCAP S500 V2 compact weather sensor."""

    DEFAULT_OUTPUTS = {
        "air_temperature": "external_temp",
        "air_humidity": "external_hum",
        "barometric_pressure": "external_pressure",
        "wind_direction_min": None,
        "wind_direction_max": None,
        "wind_direction_avg": "wind_direction",
        "wind_speed_min": None,
        "wind_speed_max": "wind_gust",
        "wind_speed_avg": "wind_speed",
        "rain_intensity": None,
        "rain_intensity_max": None,
        "rain_acc": None,
        "rain_duration": None,
    }

    def __init__(self, cfg: dict):
        super().__init__(cfg)
        self.function = int(cfg.get("function", 4))

    def _decode_block(self, registers: Sequence[int], offset: int) -> float:
        value = _convert_signed(_combine_words(registers[offset], registers[offset + 1]))
        return value / 1000.0

    def read(self, instrument_factory: InstrumentFactory) -> Dict[str, float]:
        instrument = instrument_factory(self.slave)
        primary = instrument.read_registers(0x0000, 6, functioncode=self.function)
        secondary = instrument.read_registers(0x0008, 12, functioncode=self.function)
        values = {
            "air_temperature": self._decode_block(primary, 0),
            "air_humidity": self._decode_block(primary, 2),
            "barometric_pressure": self._decode_block(primary, 4),
            "wind_direction_min": self._decode_block(secondary, 0),
            "wind_direction_max": self._decode_block(secondary, 2),
            "wind_direction_avg": self._decode_block(secondary, 4),
            "wind_speed_min": self._decode_block(secondary, 6),
            "wind_speed_max": self._decode_block(secondary, 8),
            "wind_speed_avg": self._decode_block(secondary, 10),
        }
        result: Dict[str, float] = {}
        for logical, value in values.items():
            target = self.outputs.get(logical)
            if target:
                result[target] = value
        rain_keys = {
            "rain_acc": 0x0014,
            "rain_duration": 0x0016,
            "rain_intensity": 0x0018,
            "rain_intensity_max": 0x001A,
        }
        requested_rain = [k for k in rain_keys if k in self.outputs]
        if requested_rain:
            rain_regs = instrument.read_registers(0x0014, 8, functioncode=self.function)
            for logical in requested_rain:
                start = rain_keys[logical]
                index = start - 0x0014
                if index < 0 or index + 1 >= len(rain_regs):
                    continue
                value = _convert_signed(_combine_words(rain_regs[index], rain_regs[index + 1])) / 1000.0
                target = self.outputs.get(logical)
                if target:
                    result[target] = value
        return result


DRIVER_REGISTRY: Dict[str, type[SensorDriver]] = {
    "sensecap_sco2_03b": SensecapSCO203BDriver,
    "sensecap_s500_v2": SensecapS500V2Driver,
}
