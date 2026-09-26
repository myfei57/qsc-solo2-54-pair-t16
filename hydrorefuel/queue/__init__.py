"""加注队列组件。

车辆按先来先服务排队，队列容量受限；轮到某辆车时先发起确认，确认必须在超时
前到达才允许开加注阀。确认对象带锁，保证并发确认只认第一次结果。
"""

from __future__ import annotations

from .confirm import Confirmation
from .queue import FillQueue
from .snapshot import QueueSnapshot

__all__ = ["FillQueue", "Confirmation", "QueueSnapshot"]
