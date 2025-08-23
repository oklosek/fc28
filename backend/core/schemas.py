# -*- coding: utf-8 -*-
# backend/core/schemas.py – Pydantic do API
from pydantic import BaseModel
from typing import List, Dict, Any

class VentDTO(BaseModel):
    id: int
    name: str
    position: float
    available: bool
    user_target: float

class StateDTO(BaseModel):
    mode: str
    vents: List[VentDTO]
    sensors: Dict[str, float]
    config: Dict[str, Any]
