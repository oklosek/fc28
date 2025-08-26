import sys
from pathlib import Path

sys.path.append(str(Path(__file__).resolve().parents[1]))

from backend.core.models import SensorAverager, SensorSnapshot


def test_avg_empty_queue_returns_zero():
    averager = SensorAverager()
    assert averager.avg() == 0.0


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
