"""泄漏闩锁。

泄漏触发后闩锁在保持时长内一直咬合：期间既不允许复位，也不允许重新开阀。
:meth:`is_engaged` 按当前时刻判断，保持时长走完仍需显式复位才算清除。
"""

from __future__ import annotations

import threading

from ..errors import LeakError


class LeakLatch:
    """带保持时长的泄漏闩锁。"""

    def __init__(self, hold_s: float) -> None:
        if hold_s <= 0:
            raise ValueError("保持时长必须为正")
        self._hold_s = float(hold_s)
        self._engaged = False
        self._until = 0.0
        self._cycles = 0
        self._lock = threading.RLock()

    @property
    def hold_s(self) -> float:
        return self._hold_s

    def engage(self, now: float) -> float:
        """触发闩锁，返回保持到期的时刻。"""

        with self._lock:
            self._engaged = True
            self._until = float(now) + self._hold_s
            self._cycles += 1
            return self._until

    def is_engaged(self, now: float) -> bool:
        """闩锁是否仍在保持期内。"""

        with self._lock:
            return self._engaged and float(now) < self._until

    def remaining_s(self, now: float) -> float:
        """返回保持期剩余秒数。"""

        with self._lock:
            if not self._engaged:
                return 0.0
            return max(0.0, self._until - float(now))

    def reset(self, now: float) -> bool:
        """复位闩锁，保持期未走完时拒绝。"""

        with self._lock:
            if not self._engaged:
                return False
            if float(now) < self._until:
                raise LeakError(
                    f"泄漏闩锁保持期还差 {self.remaining_s(now):.1f} 秒，不能复位",
                    component="leak",
                )
            self._engaged = False
            return True

    def cycles(self) -> int:
        """返回累计触发次数。"""

        return self._cycles
