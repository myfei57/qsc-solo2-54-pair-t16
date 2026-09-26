"""预冷保持逻辑。

仅把温度降到目标带还不够：枪口温度稳定后才允许开加注阀，因此
:class:`Precooler` 在温度进入允许带后累计保持时长，达到配置时长才置为
就绪。未就绪时开阀会被编排挡下。
"""

from __future__ import annotations

from ..config import CoolLimits

IDLE = "idle"
COOLING = "cooling"
READY = "ready"


class Precooler:
    """预冷保持计时。"""

    def __init__(self, limits: CoolLimits) -> None:
        self._limits = limits
        self._state = IDLE
        self._held_s = 0.0

    @property
    def state(self) -> str:
        return self._state

    @property
    def held_s(self) -> float:
        return self._held_s

    def start(self) -> None:
        """启动预冷保持计时。"""

        self._state = COOLING
        self._held_s = 0.0

    def tick(self, dt: float, temperature_c: float) -> bool:
        """按温度推进保持计时，返回是否已经就绪。"""

        if self._state == IDLE:
            raise ValueError("预冷尚未启动")
        if dt <= 0:
            raise ValueError("步长必须为正")
        if self._limits.reached(temperature_c):
            self._held_s += dt
        else:
            # 温度跳出允许带，保持时长清零，避免"擦边过关"。
            self._held_s = 0.0
        if self._held_s >= self._limits.precool_hold_s:
            self._state = READY
        return self._state == READY

    def is_ready(self) -> bool:
        """预冷是否已经保持足够时长。"""

        return self._state == READY

    def reset(self) -> bool:
        """复位预冷状态，返回之前是否已就绪。"""

        was_ready = self._state == READY
        self._state = IDLE
        self._held_s = 0.0
        return was_ready
