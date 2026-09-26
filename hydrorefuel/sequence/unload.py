"""卸氢顺序：软管连接 → 卸氢 → 泄压放散 → 拔管。

卸氢先按卸氢速率把槽车压力降到卸氢结束阈值，再开放散阀把余压排到拔管确认
值。压力没降到位时状态机会拒绝断开软管，编排把这次拒绝转成
``vent_before_disconnect`` 违约项，绝对不允许带压拔管。
"""

from __future__ import annotations

from ..errors import HydroError
from ..truck.machine import TruckMachine
from ..vent.latch import VentLatch
from ..vent.valve import VentValve


def unload_truck(
    truck: TruckMachine,
    vent: VentValve,
    latch: VentLatch,
    station: str,
    hose_pressure_mpa: float = 20.0,
    target_kg: float = 20.0,
    dt: float = 1.0,
    max_steps: int = 4000,
) -> dict:
    """执行一次卸氢，返回带步骤与违约项的报告。"""

    steps: list[dict] = []
    violations: list[str] = []
    try:
        truck.reset()
        pressure = truck.connect(hose_pressure_mpa)
        steps.append({"component": "truck", "action": "connect", "detail": {"pressure_mpa": round(pressure, 3)}})

        latch.engage()
        steps.append({"component": "vent", "action": "latch_engage", "detail": {"travel_mm": latch.travel()}})

        truck.open_unload()
        steps.append({"component": "truck", "action": "open_unload", "detail": {"state": truck.state}})

        for _ in range(max_steps):
            if truck.delivered_kg >= target_kg:
                break
            truck.transfer(dt)
        steps.append(
            {
                "component": "truck",
                "action": "transfer",
                "detail": {
                    "delivered_kg": round(truck.delivered_kg, 3),
                    "pressure_mpa": round(truck.pressure_mpa, 3),
                },
            }
        )
        if truck.delivered_kg + 1e-9 < target_kg:
            violations.append("unload_incomplete")

        truck.finish_unload()
        steps.append({"component": "truck", "action": "finish_unload", "detail": {"state": truck.state}})

        vent.open()
        steps.append({"component": "vent", "action": "open", "detail": {"open": vent.is_open()}})
        for _ in range(max_steps):
            if truck.discharge_ready():
                break
            bled = vent.bleed(truck.pressure_mpa, dt)
            truck.bleed(truck.pressure_mpa - bled)
        steps.append(
            {
                "component": "vent",
                "action": "vent_hold",
                "detail": {
                    "pressure_mpa": round(truck.pressure_mpa, 3),
                    "vented_mpa": round(vent.vented_mpa(), 3),
                    "ready": truck.discharge_ready(),
                },
            }
        )
        if not truck.discharge_ready():
            violations.append("vent_timeout")
        vent.close()
        latch.release()
        steps.append({"component": "vent", "action": "close", "detail": {"latch_engaged": latch.is_engaged()}})

        truck.disconnect()
        steps.append({"component": "truck", "action": "disconnect", "detail": {"state": truck.state}})
    except HydroError as error:
        payload = error.as_record()
        violations.append(f"{payload['component']}:{payload['type']}")
        steps.append({"component": payload["component"], "action": "rejected", "detail": {"message": payload["message"]}})

    return {"station": station, "ok": not violations, "steps": steps, "violations": violations}
