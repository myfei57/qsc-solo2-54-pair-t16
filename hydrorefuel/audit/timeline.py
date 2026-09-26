"""审计时间线。

把记录按时间升序排列并编号，可选地按工位过滤；控制台用它把"先泄压、再拔管"
这类跨组件顺序按发生顺序还原出来，验证顺序是否真的成立。
"""

from __future__ import annotations

from .record import AuditRecord


def build_timeline(entries: list[AuditRecord], station: str | None = None) -> list[dict]:
    """按时间升序构造时间线，返回带序号的记录列表。"""

    selected = [entry for entry in entries if station is None or entry.station == station]
    ordered = sorted(selected, key=lambda entry: entry.ts)
    return [{"step": index + 1, **entry.as_dict()} for index, entry in enumerate(ordered)]
