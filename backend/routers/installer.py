# -*- coding: utf-8 -*-
# backend/routers/installer.py – panel instalatora (ustawienia)
from fastapi import APIRouter, Depends, Body
from backend.core.config import CONTROL, VENTS, VENT_GROUPS
from backend.core.db import SessionLocal, Setting
from backend.core.security import require_admin

router = APIRouter()

@router.get("/config")
def get_config(auth=Depends(require_admin)):
    return {"control": CONTROL, "vents": VENTS, "groups": VENT_GROUPS}

@router.post("/config/control")
def set_control(payload=Body(...), auth=Depends(require_admin)):
    # Zapisuje wartości do bazy; settings.yaml aktualizować osobno
    with SessionLocal() as s:
        for k, v in payload.items():
            s.merge(Setting(key=f"control.{k}", value=str(v)))
        s.commit()
    return {"ok": True}

@router.post("/calibrate/all")
def calibrate_all(auth=Depends(require_admin)):
    from backend.app import controller
    controller.calibrate_all()
    return {"ok": True}
