# -*- coding: utf-8 -*-

from __future__ import annotations

import json
import socket
import time
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional, Set

from fastapi import APIRouter, Body, Depends, HTTPException

from backend.core.config import (
    CONTROL,
    HEATING,
    VENTS,
    VENT_GROUPS,
    VENT_PLAN_STAGES,
    VENT_PLAN_CLOSE_STRATEGY,
    EXTERNAL_CONNECTION,
    BONEIOS,
    LOG_DIR,
)
from backend.core.config_helpers import (
    build_control_fields,
    control_payload_to_model,
    heating_payload_to_model,
    boneio_payload_to_models,
    vents_payload_to_models,
    groups_payload_to_models,
    plan_payload_to_model,
    external_payload_to_model,
    export_boneio_configuration,
    export_vent_configuration,
    export_groups_configuration,
    export_plan_configuration,
    export_heating_configuration,
    export_external_configuration,
)
from backend.core.db import SessionLocal, Setting
from backend.core.installer_schemas import (
    ControlSettingsPayload,
    ControlSettingsResponse,
    HeatingConfigPayload,
    VentConfigPayload,
    VentGroupPayload,
    VentPlanPayload,
    ExternalConnectionPayload,
    BoneIODeviceConfigPayload,
    SensorOverviewResponse,
    SensorMetricSchema,
    NetworkInterfaceSchema,
    InstallerConfigSnapshot,
    ManualHistoryEntry,
    OverrideHistoryEntry,
    TestModeState,
    BoneIOVentStatus,
    BoneIODeviceStatus,
    VentTestStatus,
    TestStatusResponse,
    TestControlPayload,
    TestSimulatePayload,
    TestLogsResponse,
    TestPingPayload,
    TestPingResponse,
    TestPingResult,
)
from backend.core.panel_utils import build_sensor_overview, build_test_overview
from backend.core import test_mode
from backend.core.security import require_admin


router = APIRouter()
config_router = APIRouter(prefix="/config")
test_router = APIRouter(prefix="/test")


def _controller():
    from backend.app import controller

    return controller


def _persist_setting(key: str, value: object) -> None:
    with SessionLocal() as session:
        session.merge(Setting(key=key, value=json.dumps(value)))
        session.commit()


def _current_snapshot() -> InstallerConfigSnapshot:
    ctrl = _controller()
    boneio_models = boneio_payload_to_models(export_boneio_configuration())
    boneio_ids = [device.id for device in boneio_models]
    vent_models = vents_payload_to_models(export_vent_configuration(), boneio_ids)
    vent_ids = [vent.id for vent in vent_models]

    if ctrl:
        group_dicts = ctrl.export_groups()
        plan_dict = ctrl.export_plan()
        heating_dict = ctrl.export_heating() or export_heating_configuration()
    else:
        group_dicts = export_groups_configuration()
        plan_dict = export_plan_configuration()
        heating_dict = export_heating_configuration()

    group_models = groups_payload_to_models(group_dicts, vent_ids)
    plan_model = plan_payload_to_model(plan_dict, [group.id for group in group_models])
    heating_model = heating_payload_to_model(heating_dict)
    external_model = external_payload_to_model(export_external_configuration())

    return InstallerConfigSnapshot(
        control=dict(CONTROL),
        heating=heating_model,
        boneio=boneio_models,
        vents=vent_models,
        groups=group_models,
        plan=plan_model,
        external=external_model,
    )


LOG_KIND_PATHS = {
    "system": LOG_DIR / "system.log",
    "mqtt": LOG_DIR / "mqtt.log",
}

DEFAULT_PING_TARGETS = ("api", "internet", "external")
PING_TIMEOUT = 1.0

def _state_to_model(state: Dict[str, Any]) -> TestModeState:
    manual_entries: List[ManualHistoryEntry] = []
    for raw in state.get("manual_history", []) or []:
        data = dict(raw)
        data.setdefault("ts", time.time())
        try:
            manual_entries.append(ManualHistoryEntry(**data))
        except Exception:
            continue

    override_entries: List[OverrideHistoryEntry] = []
    for raw in state.get("override_history", []) or []:
        data = dict(raw)
        data.setdefault("ts", time.time())
        data.setdefault("values", {})
        try:
            override_entries.append(OverrideHistoryEntry(**data))
        except Exception:
            continue

    return TestModeState(
        enabled=bool(state.get("enabled", False)),
        overrides=dict(state.get("overrides", {})),
        manual_history=manual_entries,
        override_history=override_entries,
        metadata=dict(state.get("metadata", {})),
        updated_at=state.get("updated_at"),
    )


def _build_test_status(ctrl) -> TestStatusResponse:
    overview = build_test_overview(ctrl)
    sensor_overview = build_sensor_overview(ctrl)

    test_mode_state = _state_to_model(overview.get("test_mode", {}))

    boneio_devices: List[BoneIODeviceStatus] = []
    for device in overview.get("boneio", []) or []:
        vents = [BoneIOVentStatus(**vent) for vent in device.get("vents", [])]
        boneio_devices.append(
            BoneIODeviceStatus(
                device=device.get("device", "unknown"),
                vents=vents,
                all_available=bool(device.get("all_available", True)),
            )
        )

    vents_status = [VentTestStatus(**vent) for vent in overview.get("vents", []) or []]

    sensors = SensorOverviewResponse(
        metrics={name: SensorMetricSchema(**data) for name, data in sensor_overview.get("metrics", {}).items()},
        loops=sensor_overview.get("loops", {}),
        rs485=sensor_overview.get("rs485", []),
        network=[NetworkInterfaceSchema(**item) for item in sensor_overview.get("network", [])],
    )

    return TestStatusResponse(
        test_mode=test_mode_state,
        boneio=boneio_devices,
        vents=vents_status,
        sensors=sensors,
    )


def _read_log_lines(path: Path) -> List[str]:
    if not path.exists():
        return []
    try:
        with path.open("r", encoding="utf-8") as handle:
            lines = handle.readlines()
    except UnicodeDecodeError:
        with path.open("r", encoding="latin-1", errors="replace") as handle:
            lines = handle.readlines()
    return [line.rstrip("\r\n") for line in lines]


def _get_logs(kind: str, limit: int, offset: int) -> TestLogsResponse:
    key = kind.lower()
    if key not in LOG_KIND_PATHS:
        raise HTTPException(status_code=400, detail="Unsupported log kind")
    limit = max(1, min(limit, 500))
    offset = max(0, offset)
    lines = list(reversed(_read_log_lines(LOG_KIND_PATHS[key])))
    total = len(lines)
    entries = lines[offset : offset + limit]
    return TestLogsResponse(
        kind=key,
        entries=entries,
        total=total,
        offset=offset,
        limit=limit,
    )


def _ping_target(name: str, host: str, port: int) -> TestPingResult:
    start = time.perf_counter()
    try:
        with socket.create_connection((host, port), timeout=PING_TIMEOUT):
            duration = (time.perf_counter() - start) * 1000.0
            return TestPingResult(name=name, success=True, duration_ms=duration)
    except Exception as exc:
        duration = (time.perf_counter() - start) * 1000.0
        return TestPingResult(name=name, success=False, duration_ms=duration, error=str(exc))


def _ping_api() -> TestPingResult:
    start = time.perf_counter()
    duration = (time.perf_counter() - start) * 1000.0
    return TestPingResult(name="api", success=True, duration_ms=duration)


def _ping_internet() -> TestPingResult:
    return _ping_target("internet", "8.8.8.8", 53)


def _ping_external() -> TestPingResult:
    host = EXTERNAL_CONNECTION.get("host") if isinstance(EXTERNAL_CONNECTION, dict) else None
    port = EXTERNAL_CONNECTION.get("port") if isinstance(EXTERNAL_CONNECTION, dict) else None
    if not host:
        return TestPingResult(name="external", success=False, error="external_not_configured")
    try:
        port_int = int(port) if port is not None else 443
    except (TypeError, ValueError):
        port_int = 443
    if port_int <= 0:
        port_int = 443
    return _ping_target("external", str(host), port_int)


@test_router.get("/status", response_model=TestStatusResponse)
def get_test_status(_: None = Depends(require_admin)):
    ctrl = _controller()
    if not ctrl:
        raise HTTPException(status_code=503, detail="Controller is not ready yet")
    return _build_test_status(ctrl)


@test_router.post("/control", response_model=TestStatusResponse)
def control_test_mode(payload: TestControlPayload, _: None = Depends(require_admin)):
    ctrl = _controller()
    if not ctrl:
        raise HTTPException(status_code=503, detail="Controller is not ready yet")
    if payload.set_mode is None and payload.manual is None:
        raise HTTPException(status_code=400, detail="No control action specified")

    if payload.set_mode is not None:
        test_mode.set_test_mode(payload.set_mode)

    if payload.manual:
        command = payload.manual
        scope = command.scope
        value = command.value
        success = False
        if scope == "all":
            success = ctrl.manual_set_all(value)
        elif scope == "group":
            success = ctrl.manual_set_group(command.target, value)
        elif scope == "vent":
            if command.target is None:
                raise HTTPException(status_code=400, detail="Vent target is required")
            try:
                vent_id = int(command.target)
            except (TypeError, ValueError):
                raise HTTPException(status_code=400, detail="Vent target must be numeric")
            success = ctrl.manual_set_one(vent_id, value)
        if not success:
            raise HTTPException(status_code=422, detail="Manual command rejected")

    return _build_test_status(ctrl)


@test_router.post("/simulate", response_model=TestModeState)
def simulate_sensors(payload: TestSimulatePayload, _: None = Depends(require_admin)):
    state: Optional[Dict[str, Any]] = None
    if payload.reset:
        state = test_mode.clear_overrides()
    if payload.overrides:
        state = test_mode.set_overrides(payload.overrides)
    if state is None:
        state = test_mode.get_test_state()
    return _state_to_model(state)


@test_router.get("/logs", response_model=TestLogsResponse)
def get_test_logs(
    kind: str = "system",
    limit: int = 100,
    offset: int = 0,
    _: None = Depends(require_admin),
):
    return _get_logs(kind, limit, offset)


@test_router.post("/ping", response_model=TestPingResponse)
def ping_targets(
    payload: Optional[TestPingPayload] = Body(default=None),
    _: None = Depends(require_admin),
):
    request = payload or TestPingPayload()
    targets = request.targets or list(DEFAULT_PING_TARGETS)
    results: List[TestPingResult] = []
    seen: Set[str] = set()
    for target in targets:
        name = target.lower()
        if name in seen:
            continue
        seen.add(name)
        if name == "api":
            results.append(_ping_api())
        elif name == "internet":
            results.append(_ping_internet())
        elif name == "external":
            results.append(_ping_external())
        else:
            results.append(TestPingResult(name=name, success=False, error="unknown_target"))
    return TestPingResponse(results=results)


@config_router.get("", response_model=InstallerConfigSnapshot)
def get_full_config(_: None = Depends(require_admin)):
    return _current_snapshot()


@config_router.get("/control", response_model=ControlSettingsResponse)
def get_control_config(_: None = Depends(require_admin)):
    sections = build_control_fields()
    return ControlSettingsResponse(
        dashboard=sections.get("dashboard", []),
        advanced=sections.get("advanced", []),
        fields=sections.get("flat", {}),
    )


@config_router.post("/control", response_model=ControlSettingsResponse)
def update_control_config(payload: ControlSettingsPayload, _: None = Depends(require_admin)):
    sanitized_model = control_payload_to_model(payload.values)
    sanitized = sanitized_model.values

    with SessionLocal() as session:
        for key, value in sanitized.items():
            session.merge(Setting(key=f"control.{key}", value=str(value)))
        session.commit()

    ctrl = _controller()
    if ctrl:
        ctrl.update_config(control=sanitized)
    else:
        CONTROL.update(sanitized)

    sections = build_control_fields()
    return ControlSettingsResponse(
        dashboard=sections.get("dashboard", []),
        advanced=sections.get("advanced", []),
        fields=sections.get("flat", {}),
    )


@config_router.get("/heating", response_model=HeatingConfigPayload)
def get_heating_config(_: None = Depends(require_admin)):
    ctrl = _controller()
    data = ctrl.export_heating() if ctrl else export_heating_configuration()
    if not data:
        data = export_heating_configuration()
    model = heating_payload_to_model(data)
    return HeatingConfigPayload(**model.dict())


@config_router.post("/heating", response_model=HeatingConfigPayload)
def update_heating_config(payload: HeatingConfigPayload, _: None = Depends(require_admin)):
    sanitized_model = heating_payload_to_model(payload.dict(exclude_unset=True))
    sanitized = sanitized_model.dict()
    ctrl = _controller()
    if ctrl:
        ctrl.update_config(heating=sanitized)
        result = ctrl.export_heating() or sanitized
    else:
        HEATING.update(sanitized)
        result = dict(HEATING)
    _persist_setting("heating", result)
    return HeatingConfigPayload(**result)


@config_router.get("/boneio", response_model=List[BoneIODeviceConfigPayload])
def get_boneio_config(_: None = Depends(require_admin)):
    return boneio_payload_to_models(export_boneio_configuration())


@config_router.post("/boneio", response_model=List[BoneIODeviceConfigPayload])
def update_boneio_config(
    payload: List[BoneIODeviceConfigPayload] = Body(...),
    _: None = Depends(require_admin),
):
    raw_devices = [item.dict(exclude_unset=True) for item in payload]
    sanitized_models = boneio_payload_to_models(raw_devices)
    sanitized = [model.dict() for model in sanitized_models]
    current_vent_devices = {str(vent.get("boneio_device") or "boneio_main").strip() for vent in export_vent_configuration()}
    sanitized_ids = {model.id for model in sanitized_models}
    missing = sorted(device for device in current_vent_devices if device and device not in sanitized_ids)
    if missing:
        raise HTTPException(status_code=400, detail=f"Nie można usunąć urządzenia BoneIO przypisanego do wietrzników: {', '.join(missing)}")
    ctrl = _controller()
    if ctrl:
        ctrl.update_config(boneio_devices=sanitized)
    else:
        BONEIOS.clear()
        BONEIOS.extend(sanitized)
    _persist_setting("boneio_devices", sanitized)
    return sanitized_models


@config_router.get("/vents", response_model=List[VentConfigPayload])
def get_vents_config(_: None = Depends(require_admin)):
    boneio_ids = [device.id for device in boneio_payload_to_models(export_boneio_configuration())]
    return vents_payload_to_models(export_vent_configuration(), boneio_ids)



@config_router.post("/vents", response_model=List[VentConfigPayload])
def update_vents_config(
    payload: List[VentConfigPayload] = Body(...),
    _: None = Depends(require_admin),
):
    boneio_ids = [device.id for device in boneio_payload_to_models(export_boneio_configuration())]
    raw_payload = [item.dict(exclude_unset=True) for item in payload]
    sanitized_models = vents_payload_to_models(raw_payload, boneio_ids)
    sanitized = [model.dict() for model in sanitized_models]
    ctrl = _controller()
    if ctrl:
        ctrl.update_config(vents=sanitized)
    else:
        VENTS.clear()
        VENTS.extend(sanitized)
    _persist_setting("vents", sanitized)
    return sanitized_models

@config_router.get("/groups", response_model=List[VentGroupPayload])
def get_groups_config(_: None = Depends(require_admin)):
    ctrl = _controller()
    vent_models = vents_payload_to_models(export_vent_configuration())
    vent_ids = [vent.id for vent in vent_models]
    groups_raw = ctrl.export_groups() if ctrl else export_groups_configuration()
    return groups_payload_to_models(groups_raw, vent_ids)


@config_router.post("/groups", response_model=List[VentGroupPayload])
def update_groups_config(
    payload: List[VentGroupPayload] = Body(...),
    _: None = Depends(require_admin),
):
    vent_models = vents_payload_to_models(export_vent_configuration())
    vent_ids = [vent.id for vent in vent_models]
    raw_groups = [item.dict(exclude_unset=True) for item in payload]
    sanitized_models = groups_payload_to_models(raw_groups, vent_ids)
    sanitized = [model.dict() for model in sanitized_models]
    ctrl = _controller()
    if ctrl:
        ctrl.update_config(vent_groups=sanitized)
    else:
        VENT_GROUPS.clear()
        VENT_GROUPS.extend(sanitized)
    _persist_setting("vent_groups", sanitized)
    return sanitized_models


@config_router.get("/plan", response_model=VentPlanPayload)
def get_plan_config(_: None = Depends(require_admin)):
    ctrl = _controller()
    group_dicts = ctrl.export_groups() if ctrl else export_groups_configuration()
    group_ids = [str(item.get("id")) for item in group_dicts]
    plan_dict = ctrl.export_plan() if ctrl else export_plan_configuration()
    plan_model = plan_payload_to_model(plan_dict, group_ids)
    return VentPlanPayload(**plan_model.dict())


@config_router.post("/plan", response_model=VentPlanPayload)
def update_plan_config(payload: VentPlanPayload, _: None = Depends(require_admin)):
    ctrl = _controller()
    group_dicts = ctrl.export_groups() if ctrl else export_groups_configuration()
    group_ids = [str(item.get("id")) for item in group_dicts]
    sanitized_model = plan_payload_to_model(payload.dict(exclude_unset=True), group_ids)
    sanitized = sanitized_model.dict()
    if ctrl:
        ctrl.update_config(vent_plan=sanitized)
        result = ctrl.export_plan()
        plan_response = plan_payload_to_model(result, group_ids)
    else:
        global VENT_PLAN_CLOSE_STRATEGY
        VENT_PLAN_CLOSE_STRATEGY = sanitized.get("close_strategy", VENT_PLAN_CLOSE_STRATEGY)
        VENT_PLAN_STAGES.clear()
        VENT_PLAN_STAGES.extend(sanitized.get("stages", []))
        plan_response = VentPlanPayload(**sanitized)
    _persist_setting("vent_plan", sanitized)
    return plan_response


@config_router.get("/external", response_model=ExternalConnectionPayload)
def get_external_config(_: None = Depends(require_admin)):
    model = external_payload_to_model(export_external_configuration())
    return ExternalConnectionPayload(**model.dict())


@config_router.post("/external", response_model=ExternalConnectionPayload)
def update_external_config(payload: ExternalConnectionPayload, _: None = Depends(require_admin)):
    sanitized_model = external_payload_to_model(payload.dict(exclude_unset=True))
    sanitized = sanitized_model.dict()
    ctrl = _controller()
    if ctrl:
        ctrl.update_config(external=sanitized)
    else:
        EXTERNAL_CONNECTION.update(sanitized)
    _persist_setting("external_connection", sanitized)
    return ExternalConnectionPayload(**sanitized)


@config_router.get("/sensors", response_model=SensorOverviewResponse)
def get_sensor_status(_: None = Depends(require_admin)):
    ctrl = _controller()
    if not ctrl:
        raise HTTPException(status_code=503, detail="Controller is not ready yet")
    overview = build_sensor_overview(ctrl)
    metrics = {name: SensorMetricSchema(**data) for name, data in overview.get("metrics", {}).items()}
    network = [NetworkInterfaceSchema(**item) for item in overview.get("network", [])]
    return SensorOverviewResponse(
        metrics=metrics,
        loops=overview.get("loops", {}),
        rs485=overview.get("rs485", []),
        network=network,
    )


router.include_router(config_router)
router.include_router(test_router)


@router.post("/calibrate/all")
def calibrate_all(_: None = Depends(require_admin)):
    ctrl = _controller()
    if not ctrl:
        raise HTTPException(status_code=503, detail="Controller is not ready yet")
    ctrl.calibrate_all()
    return {"ok": True}
