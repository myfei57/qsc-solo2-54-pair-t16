"""质量流量与阶梯核对。"""

from __future__ import annotations

import pytest

from hydrorefuel.errors import FlowError


def test_meter_rejects_out_of_range_rate(platform):
    with pytest.raises(FlowError):
        platform.meter.commit(0.1, 10.0)
    with pytest.raises(FlowError):
        platform.meter.commit(9.0, 10.0)


def test_flow_step_tolerance(platform):
    step = platform.flow_step
    step.add(step.target_kg)
    assert step.within()
    assert step.advance() == 1
    assert step.current_kg() == 0.0
    step.add(step.target_kg + 1.0)
    assert not step.within()
