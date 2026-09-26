"""流量阶梯核对。

一个阶梯对应一段目标质量：本阶梯的累计量必须落在公差内，核对通过后才能推进
到下一个阶梯。带宽与阶梯数由配置决定，编排把每次核对结果写进审计，因此
"第几阶梯没对上"在事后可以逐条追。
"""

from __future__ import annotations

from ..config import FlowLimits


class FlowStep:
    """阶梯累计与核对。"""

    def __init__(self, limits: FlowLimits) -> None:
        self._limits = limits
        self._current_kg = 0.0
        self._steps = 0

    @property
    def target_kg(self) -> float:
        return self._limits.step_target_kg

    def add(self, mass_kg: float) -> float:
        """往本阶梯累计一段质量，返回本阶梯累计量。"""

        mass = float(mass_kg)
        if mass < 0:
            raise ValueError("阶梯增量不能为负")
        self._current_kg += mass
        return self._current_kg

    def current_kg(self) -> float:
        """返回本阶梯累计质量。"""

        return self._current_kg

    def within(self) -> bool:
        """本阶梯累计量是否落在公差内。"""

        return self._limits.within_step(self._current_kg)

    def advance(self) -> int:
        """核对通过后推进到下一阶梯，返回已完成的阶梯数。"""

        self._steps += 1
        self._current_kg = 0.0
        return self._steps

    def completed(self) -> int:
        """返回已完成的阶梯数。"""

        return self._steps
