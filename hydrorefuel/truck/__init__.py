"""槽车卸氢组件。

槽车负责软管连接、卸氢与泄压三段状态。卸氢顺序是硬性的：连接软管 → 打开
卸氢阀 → 压力下降到确认值 → 泄压放散 → 才能拔管。:class:`TruckMachine` 把
这条顺序做成状态机，压力没降到位就不允许断开软管。
"""

from __future__ import annotations

from .machine import TruckMachine
from .snapshot import TruckSnapshot

__all__ = ["TruckMachine", "TruckSnapshot"]
