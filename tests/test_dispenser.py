"""加注机加注阀、落座闩锁与停机顺序。"""

from __future__ import annotations

import pytest

from hydrorefuel.errors import InterlockError


def test_fill_valve_requires_seated_nozzle(platform):
    with pytest.raises(InterlockError):
        platform.dispenser.open_fill_valve()


def test_nozzle_seat_latch_and_release(platform):
    nozzle = platform.nozzle
    assert nozzle.seat(nozzle.seat_travel_mm - 1.0) is False
    assert nozzle.seat(nozzle.seat_travel_mm) is True
    assert nozzle.is_seated() and nozzle.is_latched()
    nozzle.unseat()
    assert not nozzle.is_seated()
    assert not nozzle.is_latched()
    assert nozzle.cycles() == 1


def test_stop_requires_isolate_first(platform):
    platform.nozzle.seat(platform.nozzle.seat_travel_mm)
    platform.dispenser.open_fill_valve()
    assert platform.dispenser.is_filling()
    with pytest.raises(InterlockError):
        platform.dispenser.stop()
    platform.dispenser.isolate()
    platform.dispenser.stop()
    assert platform.dispenser.state == "stopped"
    assert not platform.dispenser.fill_valve_open()
