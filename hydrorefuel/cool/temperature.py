"""预冷温度模型。

温度从环境温度按冷速线性下降并夹在目标温度上，供预冷保持时长判断使用。
模型是显式推进的，验证环境不需要真实等待制冷机组。
"""

from __future__ import annotations

from ..config import CoolLimits

AMBIENT_C = 25.0


class TemperatureModel:
    """加注枪口温度模型。"""

    def __init__(self, limits: CoolLimits, start_c: float = AMBIENT_C) -> None:
        self._limits = limits
        self._value_c = float(start_c)

    @property
    def limits(self) -> CoolLimits:
        return self._limits

    @property
    def value_c(self) -> float:
        return self._value_c

    def cool(self, dt: float) -> float:
        """按冷速降温一个步长，返回降温后的温度。"""

        if dt <= 0:
            raise ValueError("步长必须为正")
        self._value_c = max(self._limits.target_temp_c, self._value_c - self._limits.cool_rate_c_per_s * dt)
        return self._value_c

    def reached(self) -> bool:
        """温度是否已落到加注允许带。"""

        return self._limits.reached(self._value_c)

    def reset(self) -> None:
        """把温度恢复到环境温度。"""

        self._value_c = AMBIENT_C
