"""加注队列。

队列按先来先服务出车，容量受限；重复入队、越界出队都会直接报错。队列只保存
车辆标识与入队时刻，不掺入加注状态，避免与加注机状态机互相污染。
"""

from __future__ import annotations

from ..config import QueueLimits
from ..errors import InterlockError


class FillQueue:
    """先来先服务的加注队列。"""

    def __init__(self, limits: QueueLimits) -> None:
        self._limits = limits
        self._entries: list[tuple[str, float]] = []

    @property
    def limited(self) -> QueueLimits:
        return self._limits

    def enqueue(self, vehicle: str, now: float) -> int:
        """把车辆加入队尾，返回其排队位次。"""

        if not vehicle:
            raise InterlockError("车辆标识不能为空", component="queue")
        if self.contains(vehicle):
            raise InterlockError(f"车辆 {vehicle} 已在队列中", component="queue")
        if len(self._entries) >= self._limits.max_waiting:
            raise InterlockError("加注队列已满", component="queue")
        self._entries.append((vehicle, float(now)))
        return len(self._entries)

    def dequeue(self) -> str:
        """取出队首车辆，返回其标识。"""

        if not self._entries:
            raise InterlockError("加注队列为空", component="queue")
        vehicle, _now = self._entries.pop(0)
        return vehicle

    def contains(self, vehicle: str) -> bool:
        """车辆是否已在队列中。"""

        return any(item[0] == vehicle for item in self._entries)

    def position(self, vehicle: str) -> int:
        """返回车辆排队位次（从 1 开始），不在队列返回 0。"""

        for index, (item, _now) in enumerate(self._entries):
            if item == vehicle:
                return index + 1
        return 0

    def size(self) -> int:
        """返回队列长度。"""

        return len(self._entries)

    def waiting(self) -> list[dict]:
        """返回队列内容，含排队位次与入队时刻。"""

        return [
            {"vehicle": vehicle, "position": index + 1, "since": round(now, 3)}
            for index, (vehicle, now) in enumerate(self._entries)
        ]

    def reset(self) -> int:
        """清空队列，返回清掉的车辆数。"""

        cleared = len(self._entries)
        self._entries.clear()
        return cleared
