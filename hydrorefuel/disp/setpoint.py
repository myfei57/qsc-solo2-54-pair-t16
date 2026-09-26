"""加注压力设定点仲裁。

自动循环与手动控制台会同时向加注机提交压力设定点。仲裁按优先级取最高的一路，
优先级相同则取最新提交；仲裁结果是唯一提交值，执行器永远只看到一个设定点，
避免抢指令把加注压力抖成两段动作。
"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class SetpointOutcome:
    """一次设定点仲裁结果。"""

    winner: str
    value_mpa: float
    priority: int
    contenders: int

    def as_dict(self) -> dict:
        return {
            "winner": self.winner,
            "value_mpa": round(self.value_mpa, 3),
            "priority": self.priority,
            "contenders": self.contenders,
        }


class SetpointArbiter:
    """按优先级与提交时序仲裁加注压力设定点。"""

    def __init__(self, min_mpa: float, max_mpa: float, default_mpa: float) -> None:
        self._min = float(min_mpa)
        self._max = float(max_mpa)
        self._committed = float(default_mpa)
        self._seq = 0
        self._requests: dict[str, tuple[float, int, int]] = {}

    @property
    def limits(self) -> tuple[float, float]:
        return (self._min, self._max)

    def request(self, writer: str, value_mpa: float, priority: int) -> None:
        """登记一路设定点请求（最高优先级 + 最新提交胜出）。"""

        self._seq += 1
        clamped = max(self._min, min(self._max, float(value_mpa)))
        self._requests[writer] = (clamped, int(priority), self._seq)

    def resolve(self) -> SetpointOutcome:
        """收敛所有请求，返回并记录唯一提交值。"""

        if not self._requests:
            return SetpointOutcome("none", self._committed, 0, 0)
        winner, (value, priority, _seq) = max(
            self._requests.items(), key=lambda item: (item[1][1], item[1][2])
        )
        self._committed = value
        return SetpointOutcome(winner, value, priority, len(self._requests))

    def committed(self) -> float:
        """返回最近一次提交的设定点。"""

        return self._committed

    def writers(self) -> list[str]:
        """返回当前登记了请求的写入方。"""

        return sorted(self._requests)
