"""测试公共步骤。"""

from __future__ import annotations


def load_station(platform, hose_pressure_mpa: float = 20.0, target_kg: float = 20.0) -> dict:
    """跑一遍卸氢 + 增压充瓶，返回两次操作报告。"""

    unload = platform.unload(hose_pressure_mpa=hose_pressure_mpa, target_kg=target_kg)
    assert unload["ok"], unload["violations"]
    pressurize = platform.pressurize(inlet_pressure_mpa=12.0, flow_kg_per_min=4.0, charge_kg=12.0)
    assert pressurize["ok"], pressurize["violations"]
    return {"unload": unload, "pressurize": pressurize}
