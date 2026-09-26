"""质量流量计。

流量计按速率积分出累计质量。速率越界（低于下限或高于上限）都会直接拒绝，
避免把失控的加注算成正常流量；总量一旦超过目标即返回已满，由编排收枪。
"""

from __future__ import annotations

from ..config import FlowLimits
from ..errors import FlowError


class MassFlowMeter:
    """质量流量计与累计总量。"""

    def __init__(self, limits: FlowLimits) -> None:
        self._limits = limits
        self._rate_kg_per_min = 0.0
        self._total_kg = 0.0

    @property
    def limits(self) -> FlowLimits:
        return self._limits

    def commit(self, rate_kg_per_min: float, dt: float) -> float:
        """按速率推进一个步长，返回累计质量。"""

        rate = float(rate_kg_per_min)
        if rate < self._limits.min_rate_kg_per_min or rate > self._limits.max_rate_kg_per_min:
            raise FlowError(
                f"加注速率 {rate} 超出允许区间 "
                f"[{self._limits.min_rate_kg_per_min}, {self._limits.max_rate_kg_per_min}]",
                component="flow",
            )
        if dt <= 0:
            raise ValueError("步长必须为正")
        self._rate_kg_per_min = rate
        self._total_kg += rate * dt / 60.0
        return self._total_kg

    def rate_kg_per_min(self) -> float:
        """返回最近一次提交的速率。"""

        return self._rate_kg_per_min

    def total_kg(self) -> float:
        """返回累计质量。"""

        return self._total_kg

    def reset(self) -> None:
        """把速率与总量清零。"""

        self._rate_kg_per_min = 0.0
        self._total_kg = 0.0
