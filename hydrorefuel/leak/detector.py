"""泄漏浓度检测。

检测器记录峰值浓度与采样次数，并按配置阀值给出是否触发。触发后即使浓度回落
也不自动清除：必须由闩锁与人工复位共同决定何时恢复。
"""

from __future__ import annotations

from ..config import LeakLimits


class LeakDetector:
    """浓度采样与触发判定。"""

    def __init__(self, limits: LeakLimits) -> None:
        self._limits = limits
        self._peak_ppm = 0.0
        self._samples = 0

    @property
    def limits(self) -> LeakLimits:
        return self._limits

    def sample(self, concentration_ppm: float) -> dict:
        """记一次浓度采样，返回采样结果。"""

        value = float(concentration_ppm)
        self._samples += 1
        self._peak_ppm = max(self._peak_ppm, value)
        tripped = self._limits.tripped(value)
        return {
            "ppm": round(value, 2),
            "threshold_ppm": self._limits.threshold_ppm,
            "tripped": tripped,
            "peak_ppm": round(self._peak_ppm, 2),
        }

    def tripped(self) -> bool:
        """峰值浓度是否达到阀值。"""

        return self._limits.tripped(self._peak_ppm)

    def peak_ppm(self) -> float:
        """返回峰值浓度。"""

        return self._peak_ppm

    def samples(self) -> int:
        """返回采样次数。"""

        return self._samples

    def reset(self) -> bool:
        """清零峰值与采样次数，返回之前是否触发过。"""

        was_tripped = self.tripped()
        self._peak_ppm = 0.0
        self._samples = 0
        return was_tripped
