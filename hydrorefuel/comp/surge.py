"""喘振保护。

离心式压缩机在流量低于最小流量时会进入喘振工况，表现为压力与流量周期性
振荡。:class:`SurgeGuard` 按最小流量判据给出结论并累计跳机次数，编排据此
决定是继续升压还是立即停机。
"""

from __future__ import annotations

from ..config import CompressorLimits


class SurgeGuard:
    """最小流量喘振保护。"""

    def __init__(self, limits: CompressorLimits) -> None:
        self._limits = limits
        self._trips = 0

    def evaluate(self, flow_kg_per_min: float) -> dict:
        """按入口流量给出喘振结论。"""

        floor = self._limits.min_flow_kg_per_min
        flow = float(flow_kg_per_min)
        surge = flow < floor
        return {
            "surge": surge,
            "flow_kg_per_min": round(flow, 3),
            "floor_kg_per_min": floor,
            "margin_kg_per_min": round(flow - floor, 3),
        }

    def trip(self) -> int:
        """记一次喘振跳机，返回累计次数。"""

        self._trips += 1
        return self._trips

    def trips(self) -> int:
        """返回累计跳机次数。"""

        return self._trips
