"""审计汇总。

巡检需要的是"哪类动作、哪个组件、什么严重度各多少条"这样的计数，而不是逐条
流水。:func:`summarize` 把记录列表折成计数与最近告警，状态页与命令行共用
同一份口径。
"""

from __future__ import annotations

from .record import AuditRecord


def summarize(entries: list[AuditRecord]) -> dict:
    """把审计记录折成计数与最近告警。"""

    by_component: dict[str, int] = {}
    by_severity: dict[str, int] = {}
    by_action: dict[str, int] = {}
    for entry in entries:
        by_component[entry.component] = by_component.get(entry.component, 0) + 1
        by_severity[entry.severity] = by_severity.get(entry.severity, 0) + 1
        by_action[entry.action] = by_action.get(entry.action, 0) + 1
    alarms = [entry.as_dict() for entry in entries if entry.is_alarm()][-5:]
    return {
        "total": len(entries),
        "by_component": by_component,
        "by_severity": by_severity,
        "by_action": by_action,
        "recent_alarms": alarms,
    }
