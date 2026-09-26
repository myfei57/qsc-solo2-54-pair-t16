"""压缩机状态快照。"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class CompressorSnapshot:
    """压缩机某一时刻的状态。"""

    state: str
    pressure_mpa: float
    target_mpa: float
    starts: int
    stops: int

    def as_dict(self) -> dict:
        return {
            "state": self.state,
            "pressure_mpa": round(self.pressure_mpa, 3),
            "target_mpa": round(self.target_mpa, 3),
            "starts": self.starts,
            "stops": self.stops,
        }
