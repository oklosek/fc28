import pytest

try:
    from backend.core.config_helpers import (
        ConfigValidationError,
        sanitize_heating_payload,
        sanitize_boneio_payload,
        sanitize_vents_payload,
    )
except ModuleNotFoundError as exc:  # pragma: no cover - optional dependency
    if exc.name == 'pydantic':
        pytest.skip('pydantic not available in this environment', allow_module_level=True)
    raise


def test_sanitize_boneio_payload_rejects_duplicate_ids():
    devices = [
        {"id": "boneio_a", "base_topic": "boneio/1"},
        {"id": "boneio_a", "base_topic": "boneio/2"},
    ]
    with pytest.raises(ConfigValidationError):
        sanitize_boneio_payload(devices)


def test_sanitize_vents_payload_requires_known_device():
    vents = [
        {
            "id": 1,
            "name": "Vent 1",
            "boneio_device": "unknown",
            "travel_time_s": 30,
            "topics": {"up": "up/topic", "down": "down/topic"},
        }
    ]
    with pytest.raises(ConfigValidationError):
        sanitize_vents_payload(vents, ["boneio_a"])


def test_sanitize_vents_payload_accepts_known_device():
    vents = [
        {
            "id": 2,
            "name": "Vent 2",
            "boneio_device": "boneio_a",
            "travel_time_s": 25,
            "topics": {"up": "up/topic", "down": "down/topic"},
        }
    ]
    sanitized = sanitize_vents_payload(vents, ["boneio_a"])
    assert sanitized[0]["boneio_device"] == "boneio_a"


def test_sanitize_heating_payload_requires_valve():
    payload = {
        "enabled": True,
        "mode": "three_way_valve",
    }
    with pytest.raises(ConfigValidationError):
        sanitize_heating_payload(payload)


def test_sanitize_heating_payload_accepts_valve_settings():
    payload = {
        "enabled": True,
        "mode": "three_way_valve",
        "valve": {
            "open_topic": "farm/heating/open",
            "close_topic": "farm/heating/close",
            "stop_topic": "farm/heating/stop",
            "open_payload": "ON",
            "close_payload": "ON",
            "stop_payload": "OFF",
            "travel_time_s": "15.5",
            "reverse_pause_s": 1,
            "min_move_s": "0.8",
            "ignore_delta_percent": "2.5",
        },
    }
    sanitized = sanitize_heating_payload(payload)
    assert sanitized["mode"] == "three_way_valve"
    valve = sanitized["valve"]
    assert valve["open_topic"] == "farm/heating/open"
    assert valve["close_topic"] == "farm/heating/close"
    assert valve["travel_time_s"] == pytest.approx(15.5)
    assert valve["reverse_pause_s"] == pytest.approx(1.0)
    assert valve["min_move_s"] == pytest.approx(0.8)
    assert valve["ignore_delta_percent"] == pytest.approx(2.5)


def test_sanitize_heating_payload_rejects_negative_delta():
    payload = {
        "enabled": True,
        "mode": "three_way_valve",
        "valve": {
            "open_topic": "farm/heating/open",
            "close_topic": "farm/heating/close",
            "ignore_delta_percent": -1,
        },
    }
    with pytest.raises(ConfigValidationError):
        sanitize_heating_payload(payload)
