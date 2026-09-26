"""瓶组状态快照。"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class BufferSnapshot:
    """瓶组某一时刻的状态。"""

    pressure_mpa: float
    stored_kg: float
    capacity_kg: float
    target_mpa: float
    within_band: bool
    baseline_epoch: int
    baseline_age_s: float
    baseline_expired: bool

    def as_dict(self) -> dict:
        return {
            "pressure_mpa": round(self.pressure_mpa, 3),
            "stored_kg": round(self.stored_kg, 3),
            "capacity_kg": round(self.capacity_kg, 3),
            "target_mpa": round(self.target_mpa, 3),
            "within_band": self.within_band,
            "baseline_epoch": self.baseline_epoch,
            "baseline_age_s": round(self.baseline_age_s, 2),
            "baseline_expired": self.baseline_expired,
        }
