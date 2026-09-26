"""加注机状态机。

状态只在 ``idle``、``filling``、``stopped`` 之间切换。开加注阀要求枪已落座
并咬合闩锁；停止加注要求先隔离（关阀）再停机，顺序颠倒会被直接拒绝。
"""

from __future__ import annotations

from ..config import DispenserLimits
from ..errors import InterlockError, PressureError
from .nozzle import Nozzle
from .snapshot import DispSnapshot

IDLE = "idle"
FILLING = "filling"
STOPPED = "stopped"


class Dispenser:
    """加注机加注阀与停机顺序状态机。"""

    def __init__(self, limits: DispenserLimits, nozzle: Nozzle) -> None:
        self._limits = limits
        self._nozzle = nozzle
        self._state = IDLE
        self._valve_open = False

    @property
    def limits(self) -> DispenserLimits:
        return self._limits

    @property
    def state(self) -> str:
        return self._state

    def fill_valve_open(self) -> bool:
        """加注阀是否打开。"""

        return self._valve_open

    def is_filling(self) -> bool:
        """是否处于加注状态。"""

        return self._state == FILLING

    def check_line_pressure(self, pressure_mpa: float) -> bool:
        """核对加注管压力是否越限。"""

        pressure = float(pressure_mpa)
        if pressure > self._limits.max_line_pressure_mpa:
            raise PressureError(
                f"加注管压力 {pressure} 超过上限 {self._limits.max_line_pressure_mpa}",
                component="disp",
            )
        return True

    def open_fill_valve(self) -> None:
        """打开加注阀，要求枪落座并咬合闩锁。"""

        if self._state == FILLING:
            raise InterlockError("加注阀已经打开", component="disp")
        if not self._nozzle.is_seated() or not self._nozzle.is_latched():
            raise InterlockError("枪未落座咬合，不能打开加注阀", component="disp")
        self._valve_open = True
        self._state = FILLING

    def isolate(self) -> None:
        """隔离：关闭加注阀，切断管路。"""

        if not self._valve_open:
            raise InterlockError("加注阀未打开，无需隔离", component="disp")
        self._valve_open = False

    def stop(self) -> None:
        """停机，要求已经先隔离。"""

        if self._state != FILLING:
            raise InterlockError("只有加注中才能停机", component="disp")
        if self._valve_open:
            raise InterlockError("停机前必须先隔离（关闭加注阀）", component="disp")
        self._state = STOPPED

    def reset(self) -> bool:
        """复位加注机，返回之前是否在加注。"""

        was_filling = self._state == FILLING
        self._valve_open = False
        self._state = IDLE
        return was_filling

    def snapshot(self) -> DispSnapshot:
        """返回加注机状态快照。"""

        return DispSnapshot(
            state=self._state,
            valve_open=self._valve_open,
            nozzle_seated=self._nozzle.is_seated(),
            nozzle_latched=self._nozzle.is_latched(),
            nozzle_travel_mm=self._nozzle.travel_mm(),
            seat_cycles=self._nozzle.cycles(),
        )
