import sys
from pathlib import Path

sys.path.append(str(Path(__file__).resolve().parents[1]))

import asyncio
import time
import minimalmodbus

from backend.core.rs485 import RS485Bus


def test_no_response_does_not_block(monkeypatch):
    bus = RS485Bus(
        name="test",
        port="/dev/null",
        baudrate=9600,
        sensors=[{"slave": 1, "reg": 1, "map_to": "temp"}],
        timeout=0.1,
    )

    def fake_read_register(self, *args, **kwargs):
        time.sleep(0.05)
        raise minimalmodbus.NoResponseError("timeout")

    monkeypatch.setattr(minimalmodbus.Instrument, "read_register", fake_read_register)

    async def main():
        bus_task = asyncio.create_task(bus.read_all())
        ticks = 0

        async def ticker():
            nonlocal ticks
            while not bus_task.done():
                await asyncio.sleep(0.01)
                ticks += 1

        await ticker()
        result = await bus_task
        return ticks, result

    ticks, result = asyncio.run(main())

    assert ticks > 0
    assert result["temp"] is None
