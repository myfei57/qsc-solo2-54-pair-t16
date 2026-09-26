"""加注确认。

轮到某辆车时先发起确认，确认必须在超时前到达。确认对象加锁：并发确认只认
第一次到达的那一次，后到的请求看到的是"已确认"，不会把结果覆盖成相反结论。
"""

from __future__ import annotations

import threading


class Confirmation:
    """带超时的加注确认。"""

    def __init__(self, timeout_s: float) -> None:
        if timeout_s <= 0:
            raise ValueError("确认超时必须为正")
        self._timeout_s = float(timeout_s)
        self._pending: dict[str, float] = {}
        self._confirmed: dict[str, float] = {}
        self._lock = threading.RLock()

    @property
    def timeout_s(self) -> float:
        return self._timeout_s

    def open(self, vehicle: str, now: float) -> None:
        """为车辆发起一次确认。"""

        with self._lock:
            self._pending[vehicle] = float(now)
            self._confirmed.pop(vehicle, None)

    def confirm(self, vehicle: str, now: float) -> bool:
        """确认车辆，返回本次是否被采纳（超时或未发起都算失败）。"""

        with self._lock:
            started = self._pending.get(vehicle)
            if started is None:
                return False
            if vehicle in self._confirmed:
                # 只认第一次到达的确认，后到的请求直接判失败。
                return False
            if float(now) - started > self._timeout_s:
                return False
            self._confirmed[vehicle] = float(now)
            return True

    def pending(self, vehicle: str) -> bool:
        """车辆是否还有未完成的确认。"""

        with self._lock:
            return vehicle in self._pending and vehicle not in self._confirmed

    def expired(self, vehicle: str, now: float) -> bool:
        """车辆确认是否已经超时。"""

        with self._lock:
            started = self._pending.get(vehicle)
            if started is None:
                return False
            return float(now) - started > self._timeout_s

    def clear(self, vehicle: str) -> bool:
        """清掉车辆的确认记录，返回是否清掉了内容。"""

        with self._lock:
            had = vehicle in self._pending or vehicle in self._confirmed
            self._pending.pop(vehicle, None)
            self._confirmed.pop(vehicle, None)
            return had

    def outstanding(self) -> list[str]:
        """返回仍未确认的车辆（按发起先后）。"""

        with self._lock:
            return sorted(
                (vehicle for vehicle in self._pending if vehicle not in self._confirmed),
                key=lambda vehicle: self._pending[vehicle],
            )
