"""增压充瓶顺序：目标瓶组核对 → 压缩机启动 → 升压 → 瓶组缓存。

压缩机启动前必须先核对目标瓶组压力基线：基线过期或瓶组已越过目标带上限时
直接拒绝启动，避免按过期基线把瓶组顶到超压。升压后同步做一次喘振判据，
流量低于最小流量即记违约并停机。
"""

from __future__ import annotations

from ..buffer.bank import BufferBank
from ..buffer.baseline import BufferBaseline
from ..comp.machine import Compressor
from ..comp.surge import SurgeGuard
from ..errors import HydroError


def pressurize_buffer(
    compressor: Compressor,
    bank: BufferBank,
    baseline: BufferBaseline,
    surge: SurgeGuard,
    station: str,
    now: float = 0.0,
    inlet_pressure_mpa: float = 12.0,
    flow_kg_per_min: float = 4.0,
    charge_kg: float = 5.0,
    dt: float = 1.0,
    max_steps: int = 4000,
) -> dict:
    """执行一次增压充瓶，返回带步骤与违约项的报告。"""

    steps: list[dict] = []
    violations: list[str] = []
    check = baseline.check(bank.pressure_mpa, now)
    steps.append({"component": "buffer", "action": "baseline_check", "detail": check})
    if not check["ok"]:
        violations.append("buffer_baseline_expired" if check["expired"] else "buffer_over_target")
        return {"station": station, "ok": False, "steps": steps, "violations": violations}

    try:
        compressor.reset()
        inlet = compressor.start(inlet_pressure_mpa)
        steps.append({"component": "comp", "action": "start", "detail": {"inlet_mpa": round(inlet, 3)}})

        for _ in range(max_steps):
            if compressor.at_target():
                break
            compressor.ramp(dt)
        steps.append(
            {
                "component": "comp",
                "action": "ramp",
                "detail": {"pressure_mpa": round(compressor.pressure_mpa, 3), "target": round(compressor.limits.outlet_target_mpa, 3)},
            }
        )
        if not compressor.at_target():
            violations.append("compressor_ramp_incomplete")

        surge_result = surge.evaluate(flow_kg_per_min)
        if surge_result["surge"]:
            surge.trip()
            violations.append("compressor_surge")
        steps.append({"component": "comp", "action": "surge_check", "detail": surge_result})

        bank.fill(compressor.pressure_mpa, charge_kg)
        steps.append(
            {
                "component": "buffer",
                "action": "cache",
                "detail": {"pressure_mpa": round(bank.pressure_mpa, 3), "stored_kg": round(bank.stored_kg, 3)},
            }
        )
        compressor.stop()
        steps.append({"component": "comp", "action": "stop", "detail": {"pressure_mpa": round(compressor.pressure_mpa, 3)}})
    except HydroError as error:
        payload = error.as_record()
        violations.append(f"{payload['component']}:{payload['type']}")
        steps.append({"component": payload["component"], "action": "rejected", "detail": {"message": payload["message"]}})

    return {"station": station, "ok": not violations, "steps": steps, "violations": violations}
