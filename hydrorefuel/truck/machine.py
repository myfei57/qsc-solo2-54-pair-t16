"""槽车卸氢状态机。

状态只在 ``idle``、``connected``（软管已接）、``unloading``（卸氢阀已开）、
``drained``（卸完并断开）之间切换。卸氢按 :meth:`transfer` 显式驱动的步长
推进，压力随卸氢量与温降一起下降；断开软管前必须先把压力泄到放散确认值
以下，否则状态机直接拒绝——这就是"先泄压再拔管"的硬约束。
"""

from __future__ import annotations

from ..config import TruckLimits
from ..errors import InterlockError, PressureError
from .snapshot import TruckSnapshot

IDLE = "idle"
CONNECTED = "connected"
UNLOADING = "unloading"
DRAINED = "drained"


class TruckMachine:
    """槽车软管、卸氢与泄压状态机。"""

    def __init__(self, limits: TruckLimits) -> None:
        self._limits = limits
        self._state = IDLE
        self._pressure_mpa = 0.0
        self._delivered_kg = 0.0
        self._vents = 0

    @property
    def limits(self) -> TruckLimits:
        return self._limits

    @property
    def state(self) -> str:
        return self._state

    @property
    def pressure_mpa(self) -> float:
        return self._pressure_mpa

    @property
    def delivered_kg(self) -> float:
        return self._delivered_kg

    def connect(self, hose_pressure_mpa: float) -> float:
        """连接软管，返回接入时的压力。"""

        if self._state != IDLE:
            raise InterlockError("软管已连接，不能重复连接", component="truck")
        pressure = float(hose_pressure_mpa)
        if pressure <= 0.0:
            raise PressureError("接入压力必须为正值", component="truck")
        if pressure > self._limits.hose_pressure_max_mpa:
            raise PressureError(
                f"接入压力 {pressure} 超过软管允许的最高压力 {self._limits.hose_pressure_max_mpa}",
                component="truck",
            )
        self._pressure_mpa = pressure
        self._state = CONNECTED
        return pressure

    def open_unload(self) -> None:
        """打开卸氢阀，进入卸氢状态。"""

        if self._state != CONNECTED:
            raise InterlockError("卸氢阀只能在软管连接后打开", component="truck")
        self._state = UNLOADING

    def transfer(self, dt: float) -> float:
        """按卸氢速率推进一个步长，返回卸氢后的槽车压力。"""

        if self._state != UNLOADING:
            raise InterlockError("未在卸氢状态，不能推进卸氢", component="truck")
        if dt <= 0:
            raise ValueError("步长必须为正")
        moved_kg = self._limits.unload_rate_kg_per_min * dt / 60.0
        # 卸氢量与压力下降按同一比例折算：盘内气相减少，压力随之下降。
        drop_mpa = moved_kg * 0.09
        self._pressure_mpa = max(0.0, self._pressure_mpa - drop_mpa)
        self._delivered_kg += moved_kg
        return self._pressure_mpa

    def finish_unload(self) -> None:
        """关闭卸氢阀，回到已连接状态。"""

        if self._state != UNLOADING:
            raise InterlockError("只有卸氢中才能结束卸氢", component="truck")
        self._state = CONNECTED

    def bleed(self, drop_mpa: float) -> float:
        """记录一次放散造成的压力下降，返回放散后的压力。"""

        if self._state not in (CONNECTED, UNLOADING):
            raise InterlockError("只有已连接状态才能放散", component="truck")
        self._pressure_mpa = max(0.0, self._pressure_mpa - float(drop_mpa))
        self._vents += 1
        return self._pressure_mpa

    def discharge_ready(self) -> bool:
        """软管压力是否已降到可以拔管的水平。"""

        return self._limits.discharge_ready(self._pressure_mpa)

    def disconnect(self) -> None:
        """断开软管，返回是否成功；压力未泄到位时直接拒绝。"""

        if self._state not in (CONNECTED, UNLOADING):
            raise InterlockError("软管未连接，无需断开", component="truck")
        if not self.discharge_ready():
            raise InterlockError(
                f"软管压力 {self._pressure_mpa:.3f} MPa 尚未泄到 {self._limits.vent_confirm_mpa} MPa，"
                "必须先泄压放散再拔管",
                component="truck",
            )
        self._state = DRAINED

    def reset(self) -> bool:
        """把槽车恢复到初始状态，返回之前是否处于运行态。"""

        was_active = self._state != IDLE
        self._state = IDLE
        self._pressure_mpa = 0.0
        self._delivered_kg = 0.0
        self._vents = 0
        return was_active

    def snapshot(self) -> TruckSnapshot:
        """返回槽车状态快照。"""

        return TruckSnapshot(
            state=self._state,
            pressure_mpa=self._pressure_mpa,
            hose_connected=self._state in (CONNECTED, UNLOADING),
            delivered_kg=self._delivered_kg,
            vents=self._vents,
        )
