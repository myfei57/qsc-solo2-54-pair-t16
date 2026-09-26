"""停止加注顺序：先隔离（关加注阀）再停机。

停止加注时先关阀切断管路，再停机退出加注状态。顺序颠倒会被状态机直接拒绝，
编排把拒绝转成 ``isolate_before_stop`` 违约项，确保管路里不会留一段没有隔离
的带压气体。
"""

from __future__ import annotations

from ..disp.machine import Dispenser
from ..errors import HydroError


def stop_fill(dispenser: Dispenser, station: str) -> dict:
    """执行一次停止加注，返回带步骤与违约项的报告。"""

    steps: list[dict] = []
    violations: list[str] = []
    if not dispenser.is_filling():
        violations.append("not_filling")
        return {"station": station, "ok": False, "steps": steps, "violations": violations}
    try:
        dispenser.isolate()
        steps.append(
            {"component": "disp", "action": "isolate", "detail": {"valve_open": dispenser.fill_valve_open()}}
        )
        dispenser.stop()
        steps.append({"component": "disp", "action": "stop", "detail": {"state": dispenser.state}})
    except HydroError as error:
        payload = error.as_record()
        violations.append("isolate_before_stop")
        steps.append({"component": payload["component"], "action": "rejected", "detail": {"message": payload["message"]}})
    return {"station": station, "ok": not violations, "steps": steps, "violations": violations}
