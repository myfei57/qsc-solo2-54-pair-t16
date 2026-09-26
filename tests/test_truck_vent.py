"""槽车卸氢与泄压放散顺序。"""

from __future__ import annotations

import pytest

from hydrorefuel.errors import InterlockError, PressureError
from hydrorefuel.vent.latch import VentLatch


def test_disconnect_requires_vent(platform):
    platform.truck.connect(20.0)
    platform.truck.open_unload()
    platform.truck.transfer(1.0)
    platform.truck.finish_unload()
    assert not platform.truck.discharge_ready()
    with pytest.raises(InterlockError):
        platform.truck.disconnect()


def test_unload_sequence_vents_before_disconnect(platform):
    report = platform.unload(hose_pressure_mpa=20.0, target_kg=20.0)
    assert report["ok"], report["violations"]
    assert platform.truck.state == "drained"
    assert platform.truck.discharge_ready()
    actions = [step["action"] for step in report["steps"]]
    assert actions.index("vent_hold") < actions.index("disconnect")


def test_hose_pressure_limit(platform):
    with pytest.raises(PressureError):
        platform.truck.connect(30.0)


def test_vent_latch_cycles():
    latch = VentLatch(40.0)
    latch.engage()
    assert latch.is_engaged()
    assert latch.travel() == 40.0
    latch.release()
    assert not latch.is_engaged()
    assert (latch.cycles(), latch.resets()) == (1, 1)
