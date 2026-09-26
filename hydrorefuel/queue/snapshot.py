"""加注队列状态快照。"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class QueueSnapshot:
    """加注队列某一时刻的状态。"""

    size: int
    capacity: int
    waiting: list[dict]
    outstanding: list[str]

    def as_dict(self) -> dict:
        return {
            "size": self.size,
            "capacity": self.capacity,
            "waiting": self.waiting,
            "outstanding": self.outstanding,
        }
