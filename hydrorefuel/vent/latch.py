"""放散闩锁。

放散阀一旦开到限位就由闩锁保持，避免压差把阀门口回弹。闩锁带行程计数，
巡检据此判断阀门是否需要保养；只有显式释放后阀位才允许回到关闭位。
"""

from __future__ import annotations


class VentLatch:
    """放散阀机械闩锁。"""

    def __init__(self, travel_mm: float) -> None:
        if travel_mm <= 0:
            raise ValueError("闩锁行程必须为正")
        self._travel_mm = float(travel_mm)
        self._engaged = False
        self._traveled_mm = 0.0
        self._cycles = 0
        self._resets = 0

    @property
    def travel_mm(self) -> float:
        return self._travel_mm

    def engage(self) -> float:
        """闩锁咬合，返回咬合后的行程。"""

        if self._engaged:
            raise ValueError("闩锁已经咬合")
        self._engaged = True
        self._traveled_mm = self._travel_mm
        self._cycles += 1
        return self._traveled_mm

    def release(self) -> float:
        """释放闩锁，返回归零后的行程。"""

        if not self._engaged:
            raise ValueError("闩锁尚未咬合")
        self._engaged = False
        self._traveled_mm = 0.0
        self._resets += 1
        return self._traveled_mm

    def is_engaged(self) -> bool:
        """闩锁是否处于咬合状态。"""

        return self._engaged

    def travel(self) -> float:
        """返回当前咬合行程。"""

        return self._traveled_mm

    def cycles(self) -> int:
        """返回累计咬合次数。"""

        return self._cycles

    def resets(self) -> int:
        """返回累计释放次数。"""

        return self._resets
