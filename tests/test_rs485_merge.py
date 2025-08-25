import sys
from pathlib import Path

sys.path.append(str(Path(__file__).resolve().parents[1]))

from backend.core.rs485 import RS485Manager


def _merge(s1, s2):
    for k in s1:
        if s2.get(k) is not None:
            s1[k] = s2[k]
    return s1


def test_zero_value_overrides():
    rs = RS485Manager()
    rs.snapshot.internal_temp.add(0.0)
    s1 = {"internal_temp": 10.0}
    merged = _merge(s1, rs.averages())
    assert merged["internal_temp"] == 0.0


def test_none_value_does_not_override():
    rs = RS485Manager()
    s1 = {"internal_temp": 10.0}
    merged = _merge(s1, rs.averages())
    assert merged["internal_temp"] == 10.0
