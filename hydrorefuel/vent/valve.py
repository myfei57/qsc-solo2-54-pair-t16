"""放散阀。

放散阀只有"开"与"关"两态，但压降不是瞬时的：:meth:`bleed` 按当前压力与
孔口系数算出这一段的压降，压力越接近常压放散越慢。未开阀就调用放散会直接
报错，避免审计里出现"没开阀却压降了"的假记录。
"""

from __future__ import annotations

from ..config import VentLimits
from ..errors import InterlockError


class VentValve:
    """放散阀开闭与压降模型。"""

    def __init__(self, limits: VentLimits) -> None:
        self._limits = limits
        self._open = False
        self._bursts = 0
        self._vented_mpa = 0.0

    @property
    def limits(self) -> VentLimits:
        return self._limits

    def open(self) -> None:
        """打开放散阀。"""

        if self._open:
            raise InterlockError("放散阀已经打开", component="vent")
        self._open = True
        self._bursts += 1

    def close(self) -> None:
        """关闭放散阀。"""

        if not self._open:
            raise InterlockError("放散阀未打开，无需关闭", component="vent")
        self._open = False

    def is_open(self) -> bool:
        """放散阀是否处于打开状态。"""

        return self._open

    def bleed_rate_mpa_per_s(self, pressure_mpa: float) -> float:
        """返回当前压力下的压降速率。"""

        return self._limits.vent_rate_mpa_per_s(pressure_mpa)

    def bleed(self, pressure_mpa: float, dt: float) -> float:
        """按速率推进一个步长，返回放散后的压力。"""

        if not self._open:
            raise InterlockError("放散阀未打开，不能放散", component="vent")
        if dt <= 0:
            raise ValueError("步长必须为正")
        drop = self.bleed_rate_mpa_per_s(pressure_mpa) * dt
        remaining = max(0.0, float(pressure_mpa) - drop)
        self._vented_mpa += float(pressure_mpa) - remaining
        return remaining

    def vented_mpa(self) -> float:
        """返回累计放散掉的压力。"""

        return self._vented_mpa

    def bursts(self) -> int:
        """返回累计开阀次数。"""

        return self._bursts
