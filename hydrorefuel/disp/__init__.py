"""加注机组件。

加注机把枪位、加注阀与隔离顺序串在一起：枪必须落座并咬合闩锁才能开加注阀，
停止加注必须先隔离（关阀）再停机。:class:`SetpointArbiter` 负责把自动循环与
手动控制台提交的压力设定点收敛成唯一值。
"""

from __future__ import annotations

from .machine import Dispenser
from .nozzle import Nozzle
from .setpoint import SetpointArbiter, SetpointOutcome
from .snapshot import DispSnapshot

__all__ = ["Dispenser", "Nozzle", "SetpointArbiter", "SetpointOutcome", "DispSnapshot"]
