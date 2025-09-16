# -*- coding: utf-8 -*-
# backend/routers/installer.py – panel instalatora (ustawienia)
from fastapi import APIRouter, Depends, Body
import json
from backend.core.config import (
    CONTROL,
    VENTS,
    VENT_GROUPS,
    VENT_PLAN_STAGES,
    VENT_PLAN_CLOSE_STRATEGY,
)
from backend.core.db import SessionLocal, Setting
from backend.core.security import require_admin


def _controller():
    from backend.app import controller
    return controller


def _strategy_to_str(value, default: str) -> str:
    if isinstance(value, (int, float)):
        return "lifo" if int(value) == 1 else "fifo"
    if isinstance(value, str):
        val = value.strip().lower()
        if val in ("fifo", "lifo"):
            return val
        if val in ("1", "true", "yes"):
            return "lifo"
        if val in ("0", "false", "no"):
            return "fifo"
    return default


def _decorate_plan(plan: dict) -> dict:
    if not isinstance(plan, dict):
        plan = {"close_strategy": VENT_PLAN_CLOSE_STRATEGY, "stages": VENT_PLAN_STAGES}
    close_str = _strategy_to_str(
        plan.get("close_strategy", plan.get("close_strategy_flag")),
        VENT_PLAN_CLOSE_STRATEGY,
    )
    stages_src = plan.get("stages")
    if stages_src is None:
        stages_src = VENT_PLAN_STAGES
    stages = []
    for raw in stages_src:
        stage = dict(raw)
        stage_close = _strategy_to_str(
            stage.get("close_strategy", stage.get("close_strategy_flag")),
            close_str,
        )
        stage["close_strategy"] = stage_close
        stage["close_strategy_flag"] = 1 if stage_close == "lifo" else 0
        stages.append(stage)
    return {
        "close_strategy": close_str,
        "close_strategy_flag": 1 if close_str == "lifo" else 0,
        "stages": stages,
    }


router = APIRouter()

@router.get("/config")
def get_config(auth=Depends(require_admin)):
    ctrl = _controller()
    groups = ctrl.export_groups() if ctrl else VENT_GROUPS
    base_plan = ctrl.export_plan() if ctrl else {"close_strategy": VENT_PLAN_CLOSE_STRATEGY, "stages": VENT_PLAN_STAGES}
    plan = _decorate_plan(base_plan)
    return {"control": CONTROL, "vents": VENTS, "groups": groups, "plan": plan}

@router.post("/config/control")
def set_control(payload=Body(...), auth=Depends(require_admin)):
    # Zapisuje wartości do bazy; settings.yaml aktualizować osobno
    with SessionLocal() as s:
        for k, v in payload.items():
            s.merge(Setting(key=f"control.{k}", value=str(v)))
        s.commit()
    ctrl = _controller()
    if ctrl:
        ctrl.update_config(control=payload)
    return {"ok": True, "control": CONTROL}

@router.post("/config/groups")
def set_groups(payload=Body(...), auth=Depends(require_admin)):
    groups = payload.get("groups", []) or []
    plan = payload.get("plan") or {}
    ctrl = _controller()
    if ctrl:
        ctrl.update_config(vent_groups=groups, vent_plan=plan)
        sanitized_groups = ctrl.export_groups()
        sanitized_plan = ctrl.export_plan()
    else:
        sanitized_groups = groups
        sanitized_plan = plan if isinstance(plan, dict) else {
            "close_strategy": VENT_PLAN_CLOSE_STRATEGY,
            "stages": VENT_PLAN_STAGES,
        }
    sanitized_plan = _decorate_plan(sanitized_plan)
    with SessionLocal() as s:
        s.merge(Setting(key="vent_groups", value=json.dumps(sanitized_groups)))
        s.merge(Setting(key="vent_plan", value=json.dumps(sanitized_plan)))
        s.commit()
    return {"ok": True, "groups": sanitized_groups, "plan": sanitized_plan}

@router.post("/calibrate/all")
def calibrate_all(auth=Depends(require_admin)):
    from backend.app import controller
    controller.calibrate_all()
    return {"ok": True}
