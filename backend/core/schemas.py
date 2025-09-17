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


class VentGroupDTO(BaseModel):
    id: str
    name: str
    vents: List[int]


class SensorHistoryDTO(BaseModel):
    ts: datetime
    name: str
    value: float


class StateDTO(BaseModel):
    mode: str
    vents: List[VentDTO]
    sensors: Dict[str, Optional[float]]
    config: Dict[str, Any]
    groups: List[VentGroupDTO]

