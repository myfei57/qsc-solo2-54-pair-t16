"""储氢瓶组压力与存量。

瓶组按压力与存量两个量保存状态：压缩机充瓶按注入质量抬高压力，加注取气按
取用质量压低压力。存量到达容量上限即拒绝继续充瓶，避免瓶组超压。
"""

from __future__ import annotations

from ..config import BufferLimits
from ..errors import PressureError


class BufferBank:
    """瓶组实时压力与存量。"""

    def __init__(self, limits: BufferLimits) -> None:
        self._limits = limits
        self._pressure_mpa = 0.0
        self._stored_kg = 0.0

    @property
    def limits(self) -> BufferLimits:
        return self._limits

    @property
    def pressure_mpa(self) -> float:
        return self._pressure_mpa

    @property
    def stored_kg(self) -> float:
        return self._stored_kg

    def fill(self, pressure_mpa: float, mass_kg: float) -> float:
        """充入一段气量，返回充入后的压力；超出容量即拒绝。"""

        mass = float(mass_kg)
        if mass < 0:
            raise ValueError("充瓶质量不能为负")
        if self._stored_kg + mass > self._limits.capacity_kg + 1e-9:
            raise PressureError(
                f"瓶组存量 {self._stored_kg + mass:.2f} kg 超过容量 {self._limits.capacity_kg} kg",
                component="buffer",
            )
        self._stored_kg += mass
        self._pressure_mpa = max(self._pressure_mpa, float(pressure_mpa))
        return self._pressure_mpa

    def draw(self, mass_kg: float) -> float:
        """取用一段气量，返回取用后的压力。"""

        mass = float(mass_kg)
        if mass < 0:
            raise ValueError("取用质量不能为负")
        if mass > self._stored_kg + 1e-9:
            raise PressureError("瓶组存量不足，无法取用", component="buffer")
        fraction = 0.0 if self._stored_kg <= 0 else mass / self._stored_kg
        self._stored_kg -= mass
        self._pressure_mpa = max(0.0, self._pressure_mpa * (1.0 - fraction))
        return self._pressure_mpa

    def headroom_kg(self) -> float:
        """返回剩余可充瓶质量。"""

        return max(0.0, self._limits.capacity_kg - self._stored_kg)

    def disturb(self, delta_mpa: float) -> float:
        """模拟一次瓶组压力扰动，返回扰动后的压力。"""

        self._pressure_mpa = max(0.0, self._pressure_mpa + float(delta_mpa))
        return self._pressure_mpa

    def within_band(self) -> bool:
        """当前压力是否落在目标带内。"""

        return self._limits.within(self._pressure_mpa)

    def reset(self) -> None:
        """把瓶组压力与存量清零。"""

        self._pressure_mpa = 0.0
        self._stored_kg = 0.0
