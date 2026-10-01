"""控制台配置变更的并发仲裁、幂等与审计。

每个配置类别保存一个单调版本。安全类配置采用“先到先得”：第一笔基于当前版本
的提交生效后，其余旧版本提交一律拒绝。运行调节类配置采用“最后提交时间戳”：
版本冲突时只允许时间戳更新的一笔覆盖，时间戳更旧或相同的提交不会盖掉新值。

所有结论（生效或拒绝）都写一条审计，并把配置状态物化到 JSON 文档；重启时以
审计流水为准回放，保证状态、拒绝理由与审计口径一致。
"""

from __future__ import annotations

import threading
from dataclasses import dataclass
from math import isfinite
from typing import Any, Mapping

from .audit.record import AuditRecord
from .clock import Clock
from .config import StationConfig, config_to_mapping
from .errors import ConfigError
from .store.jsonfile import JsonStore

FIRST_WRITER_WINS = "first_writer_wins"
LAST_TIMESTAMP_WINS = "last_timestamp_wins"

# 安全联锁与设备保护限值固定先到先得；工艺运行目标/温度调节允许按最新时间戳收敛。
CATEGORY_POLICIES: dict[str, str] = {
    "truck": FIRST_WRITER_WINS,
    "vent": FIRST_WRITER_WINS,
    "comp": FIRST_WRITER_WINS,
    "buffer": LAST_TIMESTAMP_WINS,
    "cool": LAST_TIMESTAMP_WINS,
    "flow": FIRST_WRITER_WINS,
    "disp": FIRST_WRITER_WINS,
    "leak": FIRST_WRITER_WINS,
    "queue": FIRST_WRITER_WINS,
}

CONFIG_DOCUMENT = "config_changes"
APPLIED_ACTION = "config_change_applied"
REJECTED_ACTION = "config_change_rejected"


@dataclass(frozen=True)
class CategoryStatus:
    """一个配置类别的当前版本与最近生效来源。"""

    category: str
    version: int
    policy: str
    actor: str | None
    request_id: str | None
    submitted_at: float | None
    applied_at: float | None
    reason: str | None

    def as_dict(self) -> dict:
        return {
            "category": self.category,
            "version": self.version,
            "policy": self.policy,
            "actor": self.actor,
            "request_id": self.request_id,
            "submitted_at": self.submitted_at,
            "applied_at": self.applied_at,
            "reason": self.reason,
        }


class ConfigChangeManager:
    """按类别处理配置提交，并留存全部决策。"""

    def __init__(
        self,
        config: StationConfig,
        unit: str,
        clock: Clock,
        audit: Any,
        store: JsonStore,
    ) -> None:
        self._config = config
        self._unit = unit
        self._clock = clock
        self._audit = audit
        self._store = store
        self._lock = threading.RLock()
        self._categories: dict[str, CategoryStatus] = {
            category: CategoryStatus(
                category=category,
                version=0,
                policy=policy,
                actor=None,
                request_id=None,
                submitted_at=None,
                applied_at=None,
                reason=None,
            )
            for category, policy in CATEGORY_POLICIES.items()
        }
        self._outcomes: dict[str, dict] = {}
        self._order: list[str] = []
        self._outcome_limit = 10_000

    @classmethod
    def restore(
        cls,
        config: StationConfig,
        unit: str,
        clock: Clock,
        audit: Any,
        store: JsonStore,
    ) -> "ConfigChangeManager":
        """从审计流水重建配置版本与幂等请求记录。"""

        manager = cls(config, unit, clock, audit, store)
        for record in audit.replay_from_journal():
            payload = record.get("payload", {})
            if not isinstance(payload, dict):
                continue
            request_id = payload.get("request_id")
            if not isinstance(request_id, str) or not request_id:
                continue
            if record.get("action") == APPLIED_ACTION:
                manager._restore_applied(payload)
            elif record.get("action") == REJECTED_ACTION:
                manager._restore_rejected(payload)
                manager._remember_outcome(payload)
        return manager

    @property
    def config(self) -> StationConfig:
        return self._config

    def snapshot(self, limit: int = 50) -> dict:
        """返回控制台配置页需要的当前值、版本策略和最近决策。"""

        with self._lock:
            return {
                "config": config_to_mapping(self._config),
                "policies": dict(CATEGORY_POLICIES),
                "categories": {
                    category: status.as_dict() for category, status in self._categories.items()
                },
                "changes": self.recent_changes(limit),
            }

    def recent_changes(self, limit: int = 50) -> list[dict]:
        """返回最近的配置决策，最新的在前。"""

        with self._lock:
            selected = [self._outcomes[request_id] for request_id in self._order[-limit:]]
        return list(reversed(selected))

    def submit(self, request: Mapping[str, Any]) -> dict:
        """提交一笔配置变更；返回生效或拒绝结论。"""

        # 幂等键缺失时无法保证“同一请求重放”，直接按请求格式错误处理。
        request_id = self._required_text(request, "request_id")
        with self._lock:
            existing = self._outcomes.get(request_id)
            if existing is not None:
                return {**existing, "idempotent": True}

            received_at = self._clock.now()
            try:
                actor = self._required_text(request, "actor")
                reason = self._required_text(request, "reason")
                category = self._required_text(request, "category")
                if category not in CATEGORY_POLICIES:
                    raise ConfigError(f"未知配置类别 {category!r}", component="config")
                expected_version = self._expected_version(request)
                values = request.get("values", {})
                if not isinstance(values, Mapping) or not values:
                    raise ConfigError("配置变更必须包含非空 values", component="config")
                values = dict(values)
                submitted_at = self._submitted_at(
                    request,
                    received_at,
                    required=CATEGORY_POLICIES[category] == LAST_TIMESTAMP_WINS,
                )

                current_mapping = config_to_mapping(self._config)
                current_values = current_mapping["limits"][category]
                unknown = sorted(set(values) - set(current_values))
                if unknown:
                    raise ConfigError(f"配置类别 {category!r} 没有字段 {unknown!r}", component="config")
                status = self._categories[category]
                old_values = {key: current_values[key] for key in values}
                if (
                    status.policy == LAST_TIMESTAMP_WINS
                    and expected_version <= status.version
                    and status.submitted_at is not None
                    and submitted_at <= status.submitted_at
                ):
                    common = {
                        "request_id": request_id,
                        "category": category,
                        "policy": status.policy,
                        "actor": actor,
                        "reason": reason,
                        "submitted_at": submitted_at,
                        "received_at": received_at,
                        "expected_version": expected_version,
                        "version_before": status.version,
                        "values": values,
                        "old_values": old_values,
                        "idempotent": False,
                    }
                    return self._reject(
                        status,
                        common,
                        "stale_timestamp",
                        f"提交时间戳 {submitted_at} 不新于已生效时间戳 {status.submitted_at}",
                    )

                candidate_mapping = current_mapping
                candidate_mapping["limits"][category] = {**current_values, **values}
                candidate = StationConfig.from_mapping(candidate_mapping)
            except ConfigError as error:
                return self._reject_invalid_request(
                    request_id, category if "category" in locals() else "unknown", received_at, error
                )

            status = self._categories[category]
            old_values = {key: current_values[key] for key in values}
            common = {
                "request_id": request_id,
                "category": category,
                "policy": status.policy,
                "actor": actor,
                "reason": reason,
                "submitted_at": submitted_at,
                "received_at": received_at,
                "expected_version": expected_version,
                "version_before": status.version,
                "values": values,
                "old_values": old_values,
                "idempotent": False,
            }

            if status.policy == FIRST_WRITER_WINS:
                accepted, reject_code, reject_reason = self._first_writer_decision(
                    status, expected_version
                )
            else:
                accepted, reject_code, reject_reason = self._last_timestamp_decision(
                    status, expected_version, submitted_at
                )

            if accepted:
                return self._apply(candidate, status, common, received_at)
            return self._reject(status, common, reject_code, reject_reason)

    def _apply(
        self,
        candidate: StationConfig,
        status: CategoryStatus,
        common: dict,
        received_at: float,
    ) -> dict:
        new_status = CategoryStatus(
            category=status.category,
            version=status.version + 1,
            policy=status.policy,
            actor=common["actor"],
            request_id=common["request_id"],
            submitted_at=common["submitted_at"],
            applied_at=received_at,
            reason=common["reason"],
        )
        outcome = {
            **common,
            "accepted": True,
            "status": "applied",
            "version": new_status.version,
            "reject_code": None,
            "reject_reason": None,
            "current": new_status.as_dict(),
        }
        self._config = candidate
        self._categories[status.category] = new_status
        self._audit_config(
            APPLIED_ACTION,
            "notice",
            f"配置 {status.category} 已由 {common['actor']} 提交生效",
            outcome,
            received_at,
        )
        self._persist()
        self._remember_outcome(outcome)
        return dict(outcome)

    def _reject(
        self,
        status: CategoryStatus,
        common: dict,
        reject_code: str,
        reject_reason: str,
    ) -> dict:
        outcome = {
            **common,
            "accepted": False,
            "status": "rejected",
            "version": status.version,
            "reject_code": reject_code,
            "reject_reason": reject_reason,
            "current": status.as_dict(),
        }
        self._audit_config(
            REJECTED_ACTION,
            "warning",
            f"配置 {status.category} 变更被拒绝：{reject_reason}",
            outcome,
            common["received_at"],
        )
        self._persist()
        self._remember_outcome(outcome)
        return dict(outcome)

    def _reject_invalid_request(
        self,
        request_id: str,
        category: str,
        received_at: float,
        error: ConfigError,
    ) -> dict:
        """非法请求同样形成一次性、可幂等重放的拒绝结论。"""

        outcome = {
            "request_id": request_id,
            "category": category,
            "policy": CATEGORY_POLICIES.get(category),
            "actor": None,
            "reason": None,
            "submitted_at": None,
            "received_at": received_at,
            "expected_version": None,
            "version_before": self._categories.get(category).version if category in CATEGORY_POLICIES else None,
            "values": None,
            "old_values": None,
            "idempotent": False,
            "accepted": False,
            "status": "invalid",
            "version": self._categories.get(category).version if category in CATEGORY_POLICIES else None,
            "reject_code": "invalid_request",
            "reject_reason": error.message,
            "current": self._categories[category].as_dict() if category in CATEGORY_POLICIES else None,
        }
        self._audit_config(
            REJECTED_ACTION,
            "warning",
            f"配置 {category} 变更请求不合法：{error.message}",
            outcome,
            received_at,
        )
        self._persist()
        self._remember_outcome(outcome)
        return dict(outcome)

    def _audit_config(
        self,
        action: str,
        severity: str,
        message: str,
        outcome: dict,
        received_at: float,
    ) -> None:
        payload = {key: value for key, value in outcome.items() if key != "current"}
        self._audit.record(
            AuditRecord.create(
                received_at,
                self._unit,
                "config",
                action,
                severity=severity,
                message=message,
                **payload,
            )
        )

    def _persist(self) -> None:
        self._store.write(
            CONFIG_DOCUMENT,
            {
                "config": config_to_mapping(self._config),
                "categories": {
                    category: status.as_dict() for category, status in self._categories.items()
                },
                "request_ids": list(self._order),
            },
        )

    def _remember_outcome(self, outcome: Mapping[str, Any]) -> None:
        request_id = str(outcome["request_id"])
        if request_id not in self._outcomes:
            self._order.append(request_id)
            if len(self._order) > self._outcome_limit:
                expired = self._order.pop(0)
                self._outcomes.pop(expired, None)
        self._outcomes[request_id] = dict(outcome)

    def _restore_applied(self, payload: Mapping[str, Any]) -> None:
        category = str(payload.get("category", ""))
        values = payload.get("values", {})
        if category not in CATEGORY_POLICIES or not isinstance(values, Mapping):
            return
        mapping = config_to_mapping(self._config)
        mapping["limits"][category] = {**mapping["limits"][category], **dict(values)}
        self._config = StationConfig.from_mapping(mapping)
        status = CategoryStatus(
            category=category,
            version=int(payload.get("version", self._categories[category].version + 1)),
            policy=self._categories[category].policy,
            actor=_optional_text(payload.get("actor")),
            request_id=str(payload.get("request_id")),
            submitted_at=_optional_float(payload.get("submitted_at")),
            applied_at=_optional_float(payload.get("received_at")),
            reason=_optional_text(payload.get("reason")),
        )
        self._categories[category] = status
        outcome = dict(payload)
        outcome["current"] = status.as_dict()
        self._remember_outcome(outcome)

    def _restore_rejected(self, payload: Mapping[str, Any]) -> None:
        category = payload.get("category")
        if not isinstance(category, str) or category not in CATEGORY_POLICIES:
            return
        if payload.get("reject_code") in ("stale_version", "stale_timestamp", "invalid_expected_version"):
            return
        # 初始版本拒绝通常来自 version=0 的首笔非法请求，保留其当前元数据为空即可。
        version = payload.get("version_before")
        if isinstance(version, int) and not isinstance(version, bool):
            current = self._categories[category]
            new_status = CategoryStatus(
                category=category,
                version=version,
                policy=current.policy,
                actor=current.actor,
                request_id=current.request_id,
                submitted_at=current.submitted_at,
                applied_at=current.applied_at,
                reason=current.reason,
            )
            self._categories[category] = new_status
        outcome = dict(payload)
        if category in self._categories:
            outcome["current"] = self._categories[category].as_dict()
        self._remember_outcome(outcome)

    @staticmethod
    def _first_writer_decision(
        status: CategoryStatus, expected_version: int
    ) -> tuple[bool, str | None, str | None]:
        if expected_version == status.version:
            return True, None, None
        if expected_version > status.version:
            return False, "invalid_expected_version", f"期望版本 {expected_version} 高于当前版本 {status.version}"
        return (
            False,
            "stale_version",
            f"当前版本已是 {status.version}，基于版本 {expected_version} 的先到先得提交已过期",
        )

    @staticmethod
    def _last_timestamp_decision(
        status: CategoryStatus, expected_version: int, submitted_at: float
    ) -> tuple[bool, str | None, str | None]:
        if expected_version > status.version:
            return False, "invalid_expected_version", f"期望版本 {expected_version} 高于当前版本 {status.version}"
        if status.submitted_at is not None and submitted_at <= status.submitted_at:
            return (
                False,
                "stale_timestamp",
                f"提交时间戳 {submitted_at} 不新于已生效时间戳 {status.submitted_at}",
            )
        return True, None, None

    @staticmethod
    def _required_text(request: Mapping[str, Any], key: str) -> str:
        value = request.get(key)
        if not isinstance(value, str) or not value.strip():
            raise ConfigError(f"配置变更字段 {key!r} 必须是非空字符串", component="config")
        return value.strip()

    @staticmethod
    def _expected_version(request: Mapping[str, Any]) -> int:
        value = request.get("expected_version", 0)
        if isinstance(value, bool) or not isinstance(value, int) or value < 0:
            raise ConfigError("expected_version 必须是非负整数", component="config")
        return value

    @staticmethod
    def _submitted_at(request: Mapping[str, Any], default: float, *, required: bool = False) -> float:
        value = request.get("submitted_at")
        if value is None:
            if required:
                raise ConfigError("最后时间戳策略必须显式提交 submitted_at", component="config")
            return float(default)
        if isinstance(value, bool) or not isinstance(value, (int, float)) or not isfinite(float(value)):
            raise ConfigError("submitted_at 必须是有限数值时间戳", component="config")
        return float(value)


def _optional_text(value: Any) -> str | None:
    return value if isinstance(value, str) else None


def _optional_float(value: Any) -> float | None:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        return None
    return float(value)
