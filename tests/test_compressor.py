"""压缩机增压与喘振保护。"""

from __future__ import annotations

import pytest

from hydrorefuel.errors import PressureError


def test_compressor_requires_inlet_pressure(platform):
    with pytest.raises(PressureError):
        platform.compressor.start(1.0)


def test_pressurize_runs_after_buffer_check(platform):
    platform.start()
    report = platform.pressurize(inlet_pressure_mpa=12.0, flow_kg_per_min=4.0, charge_kg=12.0)
    assert report["ok"], report["violations"]
    actions = [step["action"] for step in report["steps"]]
    assert actions.index("baseline_check") < actions.index("start")
    assert platform.bank.pressure_mpa > 0
    assert platform.compressor.state == "stopped"


def test_expired_baseline_blocks_compressor(platform, clock):
    clock.advance(platform.config.buffer.baseline_ttl_s + 1.0)
    report = platform.pressurize()
    assert not report["ok"]
    assert "buffer_baseline_expired" in report["violations"]
    assert platform.compressor.state == "stopped"


def test_surge_guard_flags_low_flow(platform):
    assert platform.surge.evaluate(0.5)["surge"] is True
    assert platform.surge.evaluate(4.0)["surge"] is False
    assert platform.surge.trip() == 1
    assert platform.surge.trips() == 1
