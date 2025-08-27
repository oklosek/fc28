# -*- coding: utf-8 -*-
# backend/routers/api.py – REST API
from fastapi import APIRouter, Depends, Body
from backend.core.config import CONTROL, VENTS
from backend.core.db import SessionLocal
from backend.core.mqtt_client import sensor_bus
from backend.core.schemas import StateDTO, VentDTO
from backend.core.security import require_admin

def _controller():
    """Leniwe odwołanie do kontrolera z aplikacji głównej."""
    from backend.app import controller
    return controller

router = APIRouter()

@router.get("/state", response_model=StateDTO)
def get_state():
    controller = _controller()
    with SessionLocal() as s:
        vents = []
        for v in controller.vents.values():
            vents.append(
                VentDTO(
                    id=v.id,
                    name=v.name,
                    position=v.position,
                    available=v.available,
                    user_target=v.user_target,
                )
            )
        sensors = {
            "internal_temp": sensor_bus.internal_temp.avg(),
            "external_temp": sensor_bus.external_temp.avg(),
            "internal_hum": sensor_bus.internal_hum.avg(),
            "wind_speed": sensor_bus.wind_speed.avg(),
            "rain": sensor_bus.rain.avg(),
        }
        return StateDTO(
            mode=controller.mode, vents=vents, sensors=sensors, config=CONTROL
        )

@router.post("/mode")
def set_mode(payload=Body(...)):
    controller = _controller()
    mode = payload.get("mode", "auto")
    controller.set_mode(mode)
    return {"ok": True, "mode": controller.mode}

@router.post("/vents/all")
def set_all(p=Body(...)):
    controller = _controller()
    pct = float(p.get("position", 0))
    controller.manual_set_all(pct)
    return {"ok": True}

@router.post("/vents/{vent_id}")
def set_one(vent_id: int, p=Body(...)):
    controller = _controller()
    pct = float(p.get("position", 0))
    ok = controller.manual_set_one(vent_id, pct)
    return {"ok": ok}

# Aktualizacja z dashboardu (upload ZIP -> skrypt update)
@router.post("/admin/update")
def update_binary(auth=Depends(require_admin)):
    # W realu: przyjmij upload (multipart) i uruchom scripts/update_from_zip.sh
    return {
        "ok": True,
        "msg": "Endpoint placeholder – przygotowany do uploadu i restartu.",
    }
