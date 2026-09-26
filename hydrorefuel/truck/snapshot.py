"""槽车状态快照。"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class TruckSnapshot:
    """槽车某一时刻的状态。"""

    state: str
    pressure_mpa: float
    hose_connected: bool
    delivered_kg: float
    vents: int

    def as_dict(self) -> dict:
        return {
            "state": self.state,
            "pressure_mpa": round(self.pressure_mpa, 3),
            "hose_connected": self.hose_connected,
            "delivered_kg": round(self.delivered_kg, 3),
            "vents": self.vents,
        }
