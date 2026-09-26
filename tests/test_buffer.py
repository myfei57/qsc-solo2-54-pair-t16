"""瓶组压力核对与基线代际。"""

from __future__ import annotations


def test_baseline_check_and_calibration(platform, clock):
    baseline = platform.baseline
    fresh = baseline.check(platform.bank.pressure_mpa, clock.now())
    assert fresh["ok"]
    assert fresh["expired"] is False
    original = baseline.target_mpa
    baseline.calibrate(clock.now(), 40.0)
    assert baseline.target_mpa == 40.0
    assert baseline.epoch >= 1
    clock.advance(platform.config.buffer.baseline_ttl_s + 1.0)
    expired = baseline.check(40.0, clock.now())
    assert expired["expired"] and not expired["ok"]
    baseline.calibrate(clock.now(), original)


def test_bank_fill_and_draw(platform):
    platform.bank.fill(43.0, 20.0)
    assert platform.bank.stored_kg == 20.0
    assert platform.bank.headroom_kg() == platform.config.buffer.capacity_kg - 20.0
    pressure_before = platform.bank.pressure_mpa
    platform.bank.draw(5.0)
    assert platform.bank.stored_kg == 15.0
    assert platform.bank.pressure_mpa < pressure_before


def test_disturbance_moves_buffer(platform):
    platform.bank.fill(43.0, 20.0)
    result = platform.disturb_buffer(-1.0)
    assert result["after_mpa"] == 42.0
    assert result["within_band"] is True
