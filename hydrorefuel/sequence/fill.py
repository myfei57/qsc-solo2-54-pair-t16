"""加注顺序：队列确认 → 枪落座 → 预冷 → 开加注阀 → 阶梯流量核对 → 隔离停机。

加注是连带的硬顺序：确认超时不许落座，枪没落座咬合不许开阀，预冷没保持够
时长不许开阀，每一阶梯的累计质量必须落在公差内才允许推进下一阶梯；结束时
按"隔离 → 停机 → 枪回位"收尾。
"""

from __future__ import annotations

from ..cool.precool import Precooler
from ..cool.temperature import TemperatureModel
from ..disp.machine import Dispenser
from ..disp.nozzle import Nozzle
from ..errors import HydroError
from ..flow.meter import MassFlowMeter
from ..flow.step import FlowStep
from ..queue.confirm import Confirmation


def fill_vehicle(
    dispenser: Dispenser,
    nozzle: Nozzle,
    precooler: Precooler,
    temperature: TemperatureModel,
    meter: MassFlowMeter,
    step: FlowStep,
    confirm: Confirmation,
    station: str,
    vehicle: str = "vehicle01",
    rate_kg_per_min: float = 3.0,
    steps: int = 3,
    now: float = 0.0,
    dt: float = 36.0,
    max_steps: int = 6000,
) -> dict:
    """执行一次加注，返回带步骤与违约项的报告。"""

    log: list[dict] = []
    violations: list[str] = []

    confirm.open(vehicle, now)
    accepted = confirm.confirm(vehicle, now + 0.5)
    log.append({"component": "queue", "action": "confirm", "detail": {"vehicle": vehicle, "accepted": accepted}})
    if not accepted:
        violations.append("queue_confirm_rejected")
        return {"station": station, "vehicle": vehicle, "ok": False, "steps": log, "violations": violations}

    try:
        dispenser.reset()
        if nozzle.is_seated():
            nozzle.unseat()
        seated = nozzle.seat(nozzle.seat_travel_mm + 5.0)
        log.append(
            {
                "component": "disp",
                "action": "seat_nozzle",
                "detail": {"seated": seated, "latched": nozzle.is_latched(), "travel_mm": nozzle.travel_mm()},
            }
        )
        if not seated:
            violations.append("nozzle_not_seated")
            return {"station": station, "vehicle": vehicle, "ok": False, "steps": log, "violations": violations}

        temperature.reset()
        precooler.start()
        ready = False
        for _ in range(max_steps):
            temperature.cool(dt)
            ready = precooler.tick(dt, temperature.value_c)
            if ready:
                break
        log.append(
            {
                "component": "cool",
                "action": "precool",
                "detail": {
                    "temperature_c": round(temperature.value_c, 2),
                    "held_s": round(precooler.held_s, 2),
                    "ready": ready,
                },
            }
        )
        if not ready:
            violations.append("precool_not_ready")
            nozzle.unseat()
            return {"station": station, "vehicle": vehicle, "ok": False, "steps": log, "violations": violations}

        dispenser.open_fill_valve()
        log.append({"component": "disp", "action": "open_fill_valve", "detail": {"valve_open": dispenser.fill_valve_open()}})

        for index in range(steps):
            before = meter.total_kg()
            meter.commit(rate_kg_per_min, dt)
            step.add(meter.total_kg() - before)
            within = step.within()
            log.append(
                {
                    "component": "flow",
                    "action": "step_check",
                    "detail": {
                        "index": index + 1,
                        "mass_kg": round(step.current_kg(), 3),
                        "target_kg": round(step.target_kg, 3),
                        "within": within,
                    },
                }
            )
            if not within:
                violations.append(f"flow_step_{index + 1}_mismatch")
                break
            step.advance()

        if violations:
            # 阶梯核对未过：立即隔离停机并回枪，避免管路带压留在现场。
            dispenser.isolate()
            dispenser.stop()
            nozzle.unseat()
            log.append(
                {
                    "component": "disp",
                    "action": "abort_fill",
                    "detail": {"valve_open": dispenser.fill_valve_open(), "seated": nozzle.is_seated()},
                }
            )
        else:
            log.append(
                {
                    "component": "disp",
                    "action": "fill_complete",
                    "detail": {
                        "valve_open": dispenser.fill_valve_open(),
                        "total_kg": round(meter.total_kg(), 3),
                    },
                }
            )
    except HydroError as error:
        payload = error.as_record()
        violations.append(f"{payload['component']}:{payload['type']}")
        log.append({"component": payload["component"], "action": "rejected", "detail": {"message": payload["message"]}})
        if dispenser.fill_valve_open():
            dispenser.isolate()
            dispenser.stop()
        if nozzle.is_seated():
            nozzle.unseat()

    return {"station": station, "vehicle": vehicle, "ok": not violations, "steps": log, "violations": violations}
