"""泄漏检测与闩锁保持。"""

from __future__ import annotations

import pytest

from hydrorefuel.errors import LeakError


def test_leak_latch_holds_until_hold_expires(platform, clock):
    platform.start()
    result = platform.sample_leak(4500.0)
    assert result["tripped"]
    assert result["latch_engaged"]
    with pytest.raises(LeakError):
        platform.release_leak()
    clock.advance(platform.config.leak.hold_s + 1.0)
    assert platform.leak_latch.is_engaged(clock.now()) is False
    assert platform.release_leak()["released"] is True
    assert platform.leak_latch.cycles() == 1


def test_below_threshold_does_not_trip(platform):
    result = platform.sample_leak(100.0)
    assert not result["tripped"]
    assert platform.leak.tripped() is False
    assert platform.leak.samples() == 1
