"""充装记录审计。

审计是控制链的最后一环：每条联锁、每次加注、每次未通过的压力核对都写一条
记录，内存保留最近若干条供控制台读取，同时按段落 JSONL 供跨重启回放。
"""

from __future__ import annotations

from .log import AuditLog
from .record import AuditRecord
from .report import summarize
from .timeline import build_timeline

__all__ = ["AuditLog", "AuditRecord", "summarize", "build_timeline"]
