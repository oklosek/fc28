# -*- coding: utf-8 -*-
# backend/routers/api.py - REST API for dashboard
from typing import Dict, List

from fastapi import APIRouter, Body, Depends, HTTPException, Query

from backend.core.config import CONTROL
from backend.core.db import SessionLocal, SensorLog, Setting
from backend.core.mqtt_client import sensor_bus
from backend.core.schemas import (
    HeatingConfigDTO,
    SensorHistoryDTO,
    StateDTO,
    VentDTO,
    VentGroupDTO,
)
from backend.core.security import require_admin


def _controller():
    """Lazy reference to the controller instance from FastAPI app."""
    from backend.app import controller  # lazy import to avoid circular deps

    return controller


def _update_manager():
    """Lazy reference to the update manager instance from FastAPI app."""
    from backend.app import update_manager  # lazy import to avoid circular deps

    return update_manager


router = APIRouter()


@router.get("/state", response_model=StateDTO)
def get_state():
    controller = _controller()
    if controller is None:
        raise HTTPException(status_code=503, detail="Controller not ready")

    vent_models: List[VentDTO] = [
        VentDTO(
            id=v.id,
            name=v.name,
            position=v.position,
            available=v.available,
            user_target=v.user_target,
            boneio_device=getattr(v, "boneio_device", None),
        )
        for v in controller.vents.values()
    ]
    sensors: Dict[str, float | None] = sensor_bus.averages()
    groups = controller.export_groups() if controller else []
    heating_cfg = controller.export_heating() if controller else None
    return StateDTO(
        mode=controller.mode,
        vents=vent_models,
        sensors=sensors,
        config=dict(CONTROL),
        groups=[VentGroupDTO(**g) for g in groups],
        heating=HeatingConfigDTO(**heating_cfg) if heating_cfg else None,
    )


@router.get("/update/status")
def get_update_status():
    manager = _update_manager()
    if manager is None:
        raise HTTPException(status_code=503, detail="Updater disabled")
    return manager.status()


@router.post("/update/check")
def manual_update_check(_: None = Depends(require_admin)):
    manager = _update_manager()
    if manager is None:
        raise HTTPException(status_code=503, detail="Updater disabled")
    status = manager.check_for_updates(manual=True)
    return {"ok": True, "status": status}


@router.post("/update/run")
def manual_update_run(_: None = Depends(require_admin)):
    manager = _update_manager()
    if manager is None:
        raise HTTPException(status_code=503, detail="Updater disabled")
    result = manager.run_update()
    if not result.get("ok"):
        detail = result.get("detail", "Update failed")
        raise HTTPException(status_code=400, detail=detail)
    return result


@router.get("/history", response_model=List[SensorHistoryDTO])
def get_history(limit: int = Query(200, ge=10, le=2000)):
    with SessionLocal() as session:
        rows = (
            session.query(SensorLog)
            .order_by(SensorLog.ts.desc())
            .limit(limit)
            .all()
        )
    return [SensorHistoryDTO(ts=row.ts, name=row.name, value=row.value) for row in rows]


@router.post("/control")
def update_control(payload: Dict[str, float | int | bool]):
    controller = _controller()
    CONTROL.update(payload)
    with SessionLocal() as session:
        for key, value in payload.items():
            session.merge(Setting(key=f"control.{key}", value=str(value)))
        session.commit()
    if controller:
        controller.update_config(control=payload)
    return {"ok": True, "control": CONTROL}


@router.post("/mode")
def set_mode(payload=Body(...)):
    controller = _controller()
    if controller is None:
        raise HTTPException(status_code=503, detail="Controller not ready")
    mode = payload.get("mode", "auto")
    controller.set_mode(mode)
    return {"ok": True, "mode": controller.mode}


@router.post("/vents/all")
def set_all(p=Body(...)):
    controller = _controller()
    if controller is None:
        raise HTTPException(status_code=503, detail="Controller not ready")
    pct = float(p.get("position", 0))
    ok = controller.manual_set_all(pct)
    return {"ok": ok}


@router.post("/vents/group/{group_id}")
def set_group(group_id: str, p=Body(...)):
    controller = _controller()
    if controller is None:
        raise HTTPException(status_code=503, detail="Controller not ready")
    pct = float(p.get("position", 0))
    ok = controller.manual_set_group(group_id, pct)
    return {"ok": ok}


@router.post("/vents/{vent_id}")
def set_one(vent_id: int, p=Body(...)):
    controller = _controller()
    if controller is None:
        raise HTTPException(status_code=503, detail="Controller not ready")
    pct = float(p.get("position", 0))
    ok = controller.manual_set_one(vent_id, pct)
    return {"ok": ok}


@router.post("/admin/update")
def update_binary(_: None = Depends(require_admin)):
    manager = _update_manager()
    if manager is None:
        return {"ok": False, "msg": "Updater disabled"}
    result = manager.run_update()
    if not result.get("ok"):
        return {"ok": False, "msg": result.get("detail", "Update failed")}
    return {"ok": True, "msg": "Update applied", "status": result.get("status")}



