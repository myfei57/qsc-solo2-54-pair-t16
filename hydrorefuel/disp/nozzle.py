"""加注枪与落座闩锁。

枪插入受注口后必须走到落座行程才算到位，落座后由闩锁保持；只有闩锁咬合时
加注机才允许开加注阀。"回位后联锁释放"同样由这里体现：枪未回位就不能停机。
"""

from __future__ import annotations

from ..errors import InterlockError


class Nozzle:
    """加注枪落座与闩锁。"""

    def __init__(self, seat_travel_mm: float) -> None:
        if seat_travel_mm <= 0:
            raise ValueError("落座行程必须为正")
        self._seat_travel_mm = float(seat_travel_mm)
        self._travel_mm = 0.0
        self._seated = False
        self._latch_engaged = False
        self._cycles = 0

    @property
    def seat_travel_mm(self) -> float:
        return self._seat_travel_mm

    def seat(self, travel_mm: float) -> bool:
        """按枪位行程尝试落座，返回是否落座到位。"""

        if self._seated:
            raise InterlockError("枪已落座，不能重复落座", component="disp")
        self._travel_mm = float(travel_mm)
        if self._travel_mm >= self._seat_travel_mm:
            self._seated = True
            self._latch_engaged = True
            self._cycles += 1
        return self._seated

    def unseat(self) -> float:
        """把枪回位并释放闩锁，返回回位后的枪位行程。"""

        if not self._seated:
            raise InterlockError("枪未落座，无法回位", component="disp")
        self._seated = False
        self._latch_engaged = False
        self._travel_mm = 0.0
        return self._travel_mm

    def is_seated(self) -> bool:
        """枪是否落座到位。"""

        return self._seated

    def is_latched(self) -> bool:
        """落座闩锁是否咬合。"""

        return self._latch_engaged

    def travel_mm(self) -> float:
        """返回当前枪位行程。"""

        return self._travel_mm

    def cycles(self) -> int:
        """返回累计落座次数。"""

        return self._cycles
