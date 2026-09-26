"""压缩机状态机。

状态只在 ``stopped`` 与 ``running`` 之间切换。启动前核对入口最低压力；运行
时按配置的爬升速率逼近目标压力，不会一步跳到目标值。停机把压力提交值保持
在当前位置，便于审计对照"停在哪一档"。
"""

from __future__ import annotations

from ..config import CompressorLimits
from ..errors import InterlockError, PressureError
from .snapshot import CompressorSnapshot

STOPPED = "stopped"
RUNNING = "running"


class Compressor:
    """增压压缩机状态机。"""

    def __init__(self, limits: CompressorLimits) -> None:
        self._limits = limits
        self._state = STOPPED
        self._pressure_mpa = 0.0
        self._starts = 0
        self._stops = 0

    @property
    def limits(self) -> CompressorLimits:
        return self._limits

    @property
    def state(self) -> str:
        return self._state

    @property
    def pressure_mpa(self) -> float:
        return self._pressure_mpa

    def start(self, inlet_pressure_mpa: float) -> float:
        """启动压缩机，返回入口压力；入口压力不足即拒绝。"""

        if self._state == RUNNING:
            raise InterlockError("压缩机已在运行", component="comp")
        inlet = float(inlet_pressure_mpa)
        if inlet < self._limits.inlet_min_mpa:
            raise PressureError(
                f"入口压力 {inlet} 低于最低入口压力 {self._limits.inlet_min_mpa}",
                component="comp",
            )
        self._pressure_mpa = max(self._pressure_mpa, inlet)
        self._state = RUNNING
        self._starts += 1
        return inlet

    def ramp(self, dt: float) -> float:
        """按爬升速率逼近目标压力，返回当前出口压力。"""

        if self._state != RUNNING:
            raise InterlockError("压缩机未运行，不能升压", component="comp")
        if dt <= 0:
            raise ValueError("步长必须为正")
        step = self._limits.ramp_mpa_per_s * dt
        remaining = self._limits.outlet_target_mpa - self._pressure_mpa
        if remaining <= step:
            self._pressure_mpa = self._limits.outlet_target_mpa
        else:
            self._pressure_mpa += step
        return self._pressure_mpa

    def at_target(self) -> bool:
        """出口压力是否已经到达目标。"""

        return self._pressure_mpa >= self._limits.outlet_target_mpa - 1e-9

    def stop(self) -> float:
        """停机，返回停机时的出口压力。"""

        if self._state != RUNNING:
            raise InterlockError("压缩机未运行，无需停机", component="comp")
        self._state = STOPPED
        self._stops += 1
        return self._pressure_mpa

    def reset(self) -> bool:
        """把压缩机复位到停机零压，返回之前是否在运行。"""

        was_running = self._state == RUNNING
        self._state = STOPPED
        self._pressure_mpa = 0.0
        return was_running

    def snapshot(self) -> CompressorSnapshot:
        """返回压缩机状态快照。"""

        return CompressorSnapshot(
            state=self._state,
            pressure_mpa=self._pressure_mpa,
            target_mpa=self._limits.outlet_target_mpa,
            starts=self._starts,
            stops=self._stops,
        )
