# -*- coding: utf-8 -*-
"""Pydantic schemas dedykowane dla panelu instalatora."""
from __future__ import annotations

from typing import Any, Dict, List, Literal, Optional, Union

from pydantic import BaseModel, Field, validator


ControlScalar = Union[bool, int, float, str, None]


class ControlFieldSchema(BaseModel):
    key: str
    value: ControlScalar
    category: Literal["dashboard", "advanced"]
    type: Literal["bool", "int", "float", "str"]
    min: Optional[float] = None
    max: Optional[float] = None
    description: Optional[str] = None


class ControlSettingsResponse(BaseModel):
    dashboard: List[ControlFieldSchema] = Field(default_factory=list)
    advanced: List[ControlFieldSchema] = Field(default_factory=list)
    fields: Dict[str, ControlScalar] = Field(default_factory=dict)


class ControlSettingsPayload(BaseModel):
    values: Dict[str, ControlScalar]

    class Config:
        extra = "forbid"


class HeatingConfigPayload(BaseModel):
    enabled: bool = Field(..., description="Czy ogrzewanie jest aktywne")
    topic: Optional[str] = Field(None, description="Temat MQTT dla wyzwalania ogrzewania")
    payload_on: Optional[str] = None
    payload_off: Optional[str] = None
    day_target_c: Optional[float] = Field(None, ge=-50.0, le=80.0)
    night_target_c: Optional[float] = Field(None, ge=-50.0, le=80.0)
    hysteresis_c: Optional[float] = Field(None, ge=0.0, le=20.0)
    day_start: Optional[str] = Field(None, pattern=r"^([01]?\d|2[0-3]):[0-5]\d$")
    night_start: Optional[str] = Field(None, pattern=r"^([01]?\d|2[0-3]):[0-5]\d$")

    class Config:
        extra = "forbid"


class VentTopicConfig(BaseModel):
    up: str = Field(..., min_length=1)
    down: str = Field(..., min_length=1)
    error_in: Optional[str] = None

    class Config:
        extra = "forbid"

    @validator("up", "down", "error_in", pre=True)
    def _trim_topics(cls, value):  # noqa: D401 - simple normaliser
        if value is None:
            return value
        return str(value).strip()


class VentConfigPayload(BaseModel):
    id: int
    name: str
    boneio_device: str = Field(..., min_length=1)
    travel_time_s: float = Field(..., gt=0.0)
    topics: VentTopicConfig
    reverse_pause_s: Optional[float] = Field(None, ge=0.0)
    min_move_s: Optional[float] = Field(None, ge=0.0)
    calibration_buffer_s: Optional[float] = Field(None, ge=0.0)
    ignore_delta_percent: Optional[float] = Field(None, ge=0.0, le=100.0)

    class Config:
        extra = "forbid"

    @validator("name", "boneio_device", pre=True)
    def _strip_strings(cls, value):  # noqa: D401 - simple normaliser
        return str(value).strip()


class BoneIODeviceConfigPayload(BaseModel):
    id: str = Field(..., min_length=1)
    base_topic: str = Field(..., min_length=1)
    description: Optional[str] = None
    availability_topic: Optional[str] = None

    class Config:
        extra = "forbid"

    @validator("id", "base_topic", "description", "availability_topic", pre=True)
    def _strip_device_fields(cls, value):  # noqa: D401 - normalize strings
        if value is None:
            return value
        return str(value).strip()


class VentGroupPayload(BaseModel):
    id: str
    name: str
    vents: List[int]
    wind_upwind_deg: Optional[List[List[float]]] = None
    wind_lock_enabled: bool = True
    wind_lock_close_percent: Optional[float] = Field(None, ge=0.0, le=100.0)

    class Config:
        extra = "forbid"

    @validator("id", "name", pre=True)
    def _strip_group_strings(cls, value):  # noqa: D401 - simple normaliser
        return str(value).strip()

    @validator("vents", each_item=True)
    def _ensure_positive_vent_ids(cls, value):  # noqa: D401 - simple validator
        if value < 0:
            raise ValueError("Identyfikatory wietrznikow musza byc dodatnie")
        return value

    @validator("wind_upwind_deg")
    def _validate_wind_ranges(cls, value):  # noqa: D401 - validate ranges
        if value is None:
            return value
        cleaned: List[List[float]] = []
        for item in value:
            if not isinstance(item, (list, tuple)) or len(item) != 2:
                raise ValueError("Zakres wiatru powinien byc lista [start, end]")
            start, end = float(item[0]), float(item[1])
            if not (0.0 <= start <= 360.0 and 0.0 <= end <= 360.0):
                raise ValueError("Kat wiatru musi miescic sie w zakresie 0-360")
            cleaned.append([start, end])
        return cleaned


class VentPlanStagePayload(BaseModel):
    id: str
    name: str
    mode: Literal["serial", "parallel"] = "serial"
    step_percent: float = Field(..., gt=0.0, le=100.0)
    delay_s: float = Field(0.0, ge=0.0)
    groups: List[str]
    close_strategy_flag: Optional[int] = Field(None, ge=0, le=1)

    class Config:
        extra = "forbid"

    @validator("id", "name", pre=True)
    def _strip_stage_strings(cls, value):  # noqa: D401 - simple normaliser
        return str(value).strip()

    @validator("groups", each_item=True)
    def _strip_stage_groups(cls, value):  # noqa: D401 - simple normaliser
        return str(value).strip()

    @validator("close_strategy_flag")
    def _normalise_close_flag(cls, value):  # noqa: D401 - 0/1 normaliser
        if value is None:
            return value
        if value not in (0, 1):
            raise ValueError("close_strategy_flag powinien byc 0 lub 1")
        return int(value)


class VentPlanPayload(BaseModel):
    close_strategy: Literal["fifo", "lifo"] = "fifo"
    close_strategy_flag: Optional[int] = Field(None, ge=0, le=1)
    stages: List[VentPlanStagePayload] = Field(default_factory=list)

    class Config:
        extra = "forbid"

    @validator("close_strategy_flag")
    def _normalize_plan_flag(cls, value):  # noqa: D401 - 0/1 normaliser
        if value is None:
            return value
        if value not in (0, 1):
            raise ValueError("close_strategy_flag powinien byc 0 lub 1")
        return int(value)


class ExternalConnectionPayload(BaseModel):
    enabled: bool = False
    protocol: str = Field("https", min_length=2)
    host: Optional[str] = None
    port: int = Field(443, ge=1, le=65535)
    path: str = Field("/", min_length=1)
    token: Optional[str] = None

    class Config:
        extra = "forbid"

    @validator("protocol", "path", pre=True)
    def _strip_path(cls, value):  # noqa: D401 - simple normaliser
        if value is None:
            return value
        return str(value).strip()

    @validator("path")
    def _ensure_path_prefix(cls, value):  # noqa: D401 - ensure slash prefix
        if not value.startswith("/"):
            raise ValueError("Sciezka powinna zaczynac sie od '/'")
        return value

    @validator("token", pre=True)
    def _ensure_token_str(cls, value):  # noqa: D401 - normalise optional token
        if value is None:
            return value
        return str(value)

    @validator("host", pre=True)
    def _strip_host(cls, value):  # noqa: D401 - normalise host
        if value is None:
            return value
        return str(value).strip()

    @validator("host")
    def _require_host_when_enabled(cls, value, values):  # noqa: D401 - host presence
        enabled = values.get("enabled")
        if enabled and not value:
            raise ValueError("Wlaczenie polaczenia wymaga podania hosta")
        return value


class SensorMetricSchema(BaseModel):
    value: Optional[float] = None
    unit: Optional[str] = None
    source: Optional[str] = None


class NetworkInterfaceSchema(BaseModel):
    role: Optional[str] = None
    name: Optional[str] = None
    is_up: Optional[bool] = None
    speed_mbps: Optional[float] = None
    mtu: Optional[int] = None
    mac: Optional[str] = None
    addresses: List[str] = Field(default_factory=list)
    error: Optional[str] = None
    config: Optional[Dict[str, Any]] = None


class SensorOverviewResponse(BaseModel):
    metrics: Dict[str, SensorMetricSchema]
    loops: Dict[str, float]
    rs485: List[Dict[str, Any]]
    network: List[NetworkInterfaceSchema] = Field(default_factory=list)


class InstallerConfigSnapshot(BaseModel):
    control: Dict[str, ControlScalar]
    heating: HeatingConfigPayload
    boneio: List[BoneIODeviceConfigPayload] = Field(default_factory=list)
    vents: List[VentConfigPayload]
    groups: List[VentGroupPayload]
    plan: VentPlanPayload
    external: ExternalConnectionPayload

    class Config:
        extra = "forbid"



class ManualHistoryEntry(BaseModel):
    ts: float
    type: Optional[str] = None
    targets: Optional[List[Any]] = None
    value: Optional[float] = None

    class Config:
        extra = "allow"


class OverrideHistoryEntry(BaseModel):
    ts: float
    values: Dict[str, float] = Field(default_factory=dict)


class TestModeState(BaseModel):
    enabled: bool
    overrides: Dict[str, float] = Field(default_factory=dict)
    manual_history: List[ManualHistoryEntry] = Field(default_factory=list)
    override_history: List[OverrideHistoryEntry] = Field(default_factory=list)
    metadata: Dict[str, Any] = Field(default_factory=dict)
    updated_at: Optional[float] = None


class BoneIOVentStatus(BaseModel):
    id: int
    name: str
    available: bool


class BoneIODeviceStatus(BaseModel):
    device: str
    vents: List[BoneIOVentStatus] = Field(default_factory=list)
    all_available: bool = True


class VentTestStatus(BaseModel):
    id: int
    name: str
    position: float
    target: Optional[float] = None
    available: bool = True
    boneio_device: Optional[str] = None


class TestStatusResponse(BaseModel):
    test_mode: TestModeState
    boneio: List[BoneIODeviceStatus] = Field(default_factory=list)
    vents: List[VentTestStatus] = Field(default_factory=list)
    sensors: SensorOverviewResponse


class ManualControlCommand(BaseModel):
    scope: Literal["all", "group", "vent"]
    target: Optional[str] = None
    value: float = Field(..., ge=0.0, le=100.0)

    @validator("target", always=True)
    def _validate_target(cls, value, values):  # noqa: D401 - ensure target when needed
        scope = values.get("scope")
        if scope in {"group", "vent"} and not value:
            raise ValueError("target is required for group/vent scope")
        return value


class TestControlPayload(BaseModel):
    set_mode: Optional[bool] = None
    manual: Optional[ManualControlCommand] = None

    class Config:
        extra = "forbid"


class TestSimulatePayload(BaseModel):
    overrides: Optional[Dict[str, float]] = None
    reset: bool = False

    class Config:
        extra = "forbid"


class TestLogsResponse(BaseModel):
    kind: Literal["system", "mqtt"]
    entries: List[str]
    total: int
    offset: int
    limit: int


class TestPingPayload(BaseModel):
    targets: Optional[List[Literal["api", "internet", "external"]]] = None

    class Config:
        extra = "forbid"


class TestPingResult(BaseModel):
    name: str
    success: bool
    duration_ms: Optional[float] = None
    error: Optional[str] = None


class TestPingResponse(BaseModel):
    results: List[TestPingResult]

