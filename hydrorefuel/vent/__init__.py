"""放散组件。

放散阀负责把软管与管路里的余压排到确认值以下；机械闩锁保证放散过程中阀位
不被压差顶回，放散结束后才能释放闩锁。阀位、闩锁与压降速率三者一起决定
"能不能安全拔管"。
"""

from __future__ import annotations

from .latch import VentLatch
from .snapshot import VentSnapshot
from .valve import VentValve

__all__ = ["VentValve", "VentLatch", "VentSnapshot"]
