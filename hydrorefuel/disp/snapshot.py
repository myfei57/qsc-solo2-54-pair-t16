"""加注机状态快照。"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class DispSnapshot:
    """加注机某一时刻的状态。"""

    state: str
    valve_open: bool
    nozzle_seated: bool
    nozzle_latched: bool
    nozzle_travel_mm: float
    seat_cycles: int

    def as_dict(self) -> dict:
        return {
            "state": self.state,
            "valve_open": self.valve_open,
            "nozzle_seated": self.nozzle_seated,
            "nozzle_latched": self.nozzle_latched,
            "nozzle_travel_mm": round(self.nozzle_travel_mm, 2),
            "seat_cycles": self.seat_cycles,
        }
