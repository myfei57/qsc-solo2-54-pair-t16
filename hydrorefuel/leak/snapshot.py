"""泄漏检测状态快照。"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class LeakSnapshot:
    """泄漏检测某一时刻的状态。"""

    peak_ppm: float
    threshold_ppm: float
    tripped: bool
    latch_engaged: bool
    remaining_s: float
    cycles: int

    def as_dict(self) -> dict:
        return {
            "peak_ppm": round(self.peak_ppm, 2),
            "threshold_ppm": round(self.threshold_ppm, 2),
            "tripped": self.tripped,
            "latch_engaged": self.latch_engaged,
            "remaining_s": round(self.remaining_s, 1),
            "cycles": self.cycles,
        }
