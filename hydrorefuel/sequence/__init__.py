"""跨组件操作编排。

每个操作都是真实的跨模块调用链，顺序在编排里写死：卸氢按"软管连接 → 卸氢
阀开 → 卸氢 → 泄压放散 → 拔管"，增压充瓶按"目标瓶组核对 → 压缩机启动 →
升压 → 瓶组缓存"，加注按"队列确认 → 枪落座 → 预冷 → 开加注阀 → 压力阶梯与
流量核对 → 隔离停机 → 枪回位"。顺序被破坏时返回 violations，由平台写审计。
"""

from __future__ import annotations

from .fill import fill_vehicle
from .pressurize import pressurize_buffer
from .stop import stop_fill
from .unload import unload_truck

__all__ = ["unload_truck", "pressurize_buffer", "fill_vehicle", "stop_fill"]
