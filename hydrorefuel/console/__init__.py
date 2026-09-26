"""控制台 HTTP 服务。

控制台把平台的查询与动作接口翻译成 JSON：状态页、拓扑、命名空间、审计、
趋势、队列与就绪判据，以及卸氢、增压、加注、停止、泄漏采样与并发探测等动作。
"""

from __future__ import annotations

from .api import Api
from .server import ConsoleServer, probe_endpoints

__all__ = ["Api", "ConsoleServer", "probe_endpoints"]
