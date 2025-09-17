import sys
from pathlib import Path

sys.path.append(str(Path(__file__).resolve().parents[1]))

from backend.core.models import SensorAverager, SensorSnapshot


def test_avg_empty_queue_returns_none():
    averager = SensorAverager()
    assert averager.avg() is None


def test_avg_with_less_than_window_values():
    averager = SensorAverager()
    values = [1.0, 2.0, 3.0]
    for v in values:
        averager.add(v)
    assert averager.avg() == sum(values) / len(values)


def test_queue_limited_to_window_size():
    averager = SensorAverager()
    window = averager.window
    for v in range(window + 2):
        averager.add(float(v))
    assert len(averager.q) == window
    assert list(averager.q) == [float(v) for v in range(2, window + 2)]


def test_sensor_snapshot_individual_windows():
    snap = SensorSnapshot()
    snap.set_window(1)
    snap.set_windows({"internal_temp": 3, "wind_speed": 4})
    assert snap.internal_temp.window == 3
    assert snap.wind_speed.window == 4
    assert snap.external_temp.window == 1


def test_sensor_snapshot_averages_handles_empty_and_values():
    snap = SensorSnapshot()
    averages = snap.averages()
    assert all(value is None for value in averages.values())
    expected = {
        "internal_temp",
        "external_temp",
        "internal_hum",
        "external_hum",
        "internal_co2",
        "external_pressure",
        "wind_speed",
        "wind_gust",
        "wind_direction",
        "rain",
    }
    assert expected.issubset(set(averages.keys()))

    snap.internal_temp.add(10.0)
    snap.internal_temp.add(14.0)
    averages = snap.averages()
    assert averages["internal_temp"] == 12.0
    assert averages["external_temp"] is None
    assert averages["internal_hum"] is None
    assert averages["wind_speed"] is None
    assert averages["rain"] is None
