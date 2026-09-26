"""预冷状态快照。"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class CoolSnapshot:
    """预冷某一时刻的状态。"""

    state: str
    temperature_c: float
    target_c: float
    held_s: float
    ready: bool

    def as_dict(self) -> dict:
        return {
            "state": self.state,
            "temperature_c": round(self.temperature_c, 2),
            "target_c": round(self.target_c, 2),
            "held_s": round(self.held_s, 2),
            "ready": self.ready,
        }
