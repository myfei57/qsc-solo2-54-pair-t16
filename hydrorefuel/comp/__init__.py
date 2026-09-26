"""压缩机增压组件。

压缩机把槽车来的氢气升压送进瓶组。启动前必须核对瓶组目标压力与基线是否
有效、入口压力是否足够；运行中按爬升速率逼近目标压力，并由喘振保护监视
最小流量。任一前置条件不满足都直接拒绝启动。
"""

from __future__ import annotations

from .machine import Compressor
from .snapshot import CompressorSnapshot
from .surge import SurgeGuard

__all__ = ["Compressor", "SurgeGuard", "CompressorSnapshot"]
