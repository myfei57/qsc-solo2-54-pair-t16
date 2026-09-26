"""泄漏检测组件。

泄漏检测按采样窗口读浓度，达到阀值即触发并保持闩锁；闩锁在保持时长内不允许
复位，也不允许重新开加注阀。放散必须先于重新加注，这条约束由闩锁与编排共同
保证。
"""

from __future__ import annotations

from .detector import LeakDetector
from .latch import LeakLatch
from .snapshot import LeakSnapshot

__all__ = ["LeakDetector", "LeakLatch", "LeakSnapshot"]
