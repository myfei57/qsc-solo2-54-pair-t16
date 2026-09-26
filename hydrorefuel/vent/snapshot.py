"""放散状态快照。"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class VentSnapshot:
    """放散阀某一时刻的状态。"""

    open: bool
    latch_engaged: bool
    latch_travel_mm: float
    latch_cycles: int
    latch_resets: int
    bursts: int
    vented_mpa: float

    def as_dict(self) -> dict:
        return {
            "open": self.open,
            "latch_engaged": self.latch_engaged,
            "latch_travel_mm": round(self.latch_travel_mm, 2),
            "latch_cycles": self.latch_cycles,
            "latch_resets": self.latch_resets,
            "bursts": self.bursts,
            "vented_mpa": round(self.vented_mpa, 3),
        }
