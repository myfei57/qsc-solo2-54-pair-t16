"""流量状态快照。"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class FlowSnapshot:
    """流量某一时刻的状态。"""

    rate_kg_per_min: float
    total_kg: float
    step_kg: float
    step_target_kg: float
    steps_completed: int
    within_step: bool

    def as_dict(self) -> dict:
        return {
            "rate_kg_per_min": round(self.rate_kg_per_min, 3),
            "total_kg": round(self.total_kg, 3),
            "step_kg": round(self.step_kg, 3),
            "step_target_kg": round(self.step_target_kg, 3),
            "steps_completed": self.steps_completed,
            "within_step": self.within_step,
        }
