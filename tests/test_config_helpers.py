import pytest

try:
    from backend.core.config_helpers import (
        ConfigValidationError,
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
