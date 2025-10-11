# -*- coding: utf-8 -*-
# backend/core/schemas.py - Pydantic models for API responses
from datetime import datetime
from pydantic import BaseModel
from typing import Any, Dict, List, Optional


class VentDTO(BaseModel):
    id: int
    name: str
    position: float
    available: bool
    user_target: float
    boneio_device: Optional[str] = None


class VentGroupDTO(BaseModel):
    id: str
    name: str
    vents: List[int]
    wind_upwind_deg: Optional[List[List[float]]] = None
    wind_lock_enabled: bool = True
    wind_lock_close_percent: Optional[float] = None


class SensorHistoryDTO(BaseModel):
    ts: datetime
    name: str
    value: float


class HeatingValveDTO(BaseModel):
    open_topic: Optional[str] = None
    close_topic: Optional[str] = None
    stop_topic: Optional[str] = None
    open_payload: Optional[str] = None
    close_payload: Optional[str] = None
    stop_payload: Optional[str] = None
    travel_time_s: Optional[float] = None
    reverse_pause_s: Optional[float] = None
    min_move_s: Optional[float] = None
    ignore_delta_percent: Optional[float] = None


class HeatingConfigDTO(BaseModel):
    enabled: bool
    topic: Optional[str] = None
    payload_on: Optional[str] = None
    payload_off: Optional[str] = None
    day_target_c: Optional[float] = None
    night_target_c: Optional[float] = None
    hysteresis_c: Optional[float] = None
    day_start: Optional[str] = None
    night_start: Optional[str] = None
    mode: str = "binary"
    valve: Optional[HeatingValveDTO] = None

class StateDTO(BaseModel):
    mode: str
    vents: List[VentDTO]
    sensors: Dict[str, Optional[float]]
    config: Dict[str, Any]
    groups: List[VentGroupDTO]
    heating: Optional[HeatingConfigDTO] = None


