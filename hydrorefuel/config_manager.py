"""运行期配置的乐观并发控制。

每个配置类别维护独立版本号：控制台先读版本，再带 ``expected_version`` 提交。
安全联锁类使用 ``first_wins``，同一版本只接受第一笔；工艺调节类使用
``last_commit_ts``，同一并发代际内按提交时间戳取最新一笔，时间戳相同则按
服务端接收序号打破平局。所有接受与拒绝都写审计，``request_id`` 保证重试
幂等：同一请求重放只返回原结论，不会再次生效或追加审计。
"""

from __future__ import annotations

import dataclasses
import json
import math
import threading
import uuid
from collections.abc import Callable
from typing import Any

from .audit.log import AuditLog
from .clock import Clock
from .config import (
    BufferLimits,
    CompressorLimits,
    ConfigError,
    CoolLimits,
    DispenserLimits,
    FlowLimits,
    LeakLimits,
    QueueLimits,
    StationConfig,
    TruckLimits,
    VentLimits,
    config_to_mapping,
)
from .eventbus import Event, EventBus
from .store.jsonfile import JsonStore

FIRST_WINS = "first_wins"
LAST_COMMIT_TS = "last_commit_ts"

ACTION_ACCEPTED = "config_change_accepted"
ACTION_REJECTED = "config_change_rejected"
ACTION_REQUEST_CONFLICT = "config_request_conflict"

# 安全联锁限值采用先到先得，避免后写入的旧页面覆盖新保护值；工艺目标、带宽、
# 流量和队列容量允许同一代际按提交时间戳取最后一笔。
CATEGORY_POLICIES: dict[str, str] = {
    "truck": FIRST_WINS,
    "vent": FIRST_WINS,
    "comp": FIRST_WINS,
    "buffer": FIRST_WINS,
    "cool": LAST_COMMIT_TS,
    "flow": LAST_COMMIT_TS,
    "disp": FIRST_WINS,
    "leak": FIRST_WINS,
    "queue": LAST_COMMIT_TS,
}

_CATEGORY_CLASSES: dict[str, type] = {
    "truck": TruckLimits,
    "vent": VentLimits,
    "comp": CompressorLimits,
    "buffer": BufferLimits,
    "cool": CoolLimits,
    "flow": FlowLimits,
    "disp": DispenserLimits,
    "leak": LeakLimits,
    "queue": QueueLimits,
}


class ConfigManager:
    """带版本、冲突策略与审计重放的运行期配置存储。"""

    def __init__(
        self,
        config: StationConfig,
        bus: EventBus,
        audit: AuditLog,
        store: JsonStore,
        clock: Clock,
        unit: str,
    ) -> None:
        self._config = config
        self._bus = bus
        self._audit = audit
        self._store = store
        self._clock = clock
        self._unit = unit
        self._lock = threading.RLock()
        self._seq = 0
        self._results: dict[str, dict] = {}
        self._fingerprints: dict[str, str] = {}
        self._states: dict[str, dict] = {
            category: self._initial_state(category) for category in CATEGORY_POLICIES
        }
        self._replay()
        self._restore_request_index()

    def current_config(self) -> StationConfig:
        """返回当前生效的完整配置。"""

        with self._lock:
            return self._config

    def status(self) -> dict:
        """返回控制台配置页所需的当前值、版本、策略与最近拒绝原因。"""

        with self._lock:
            return {
                "unit": self._unit,
                "config": config_to_mapping(self._config),
                "policies": dict(CATEGORY_POLICIES),
                "categories": {
                    category: self._state_dict(category) for category in CATEGORY_POLICIES
                },
            }

    def submit(
        self,
        category: str,
        values: dict,
        *,
        expected_version: Any,
        submitted_at: Any,
        actor: Any,
        reason: Any,
        request_id: Any = None,
        apply_config: Callable[[StationConfig], None] | None = None,
    ) -> dict:
        """提交一笔类别级配置补丁；返回接受或拒绝结论。"""

        with self._lock:
            if category not in CATEGORY_POLICIES:
                raise ConfigError(f"未知配置类别 {category!r}", component="config")

            resolved_request = request_id if isinstance(request_id, str) and request_id.strip() else uuid.uuid4().hex
            resolved_request = resolved_request.strip()
            invalid = self._validate_request(values, expected_version, submitted_at, actor, reason)
            normalized: dict
            if invalid is None:
                try:
                    normalized = self._normalized_request(
                        category, values, expected_version, submitted_at, actor, reason
                    )
                except (TypeError, ValueError):
                    invalid = "配置补丁取值必须是数值"
                    normalized = {
                        "category": category,
                        "values": dict(values),
                        "expected_version": expected_version,
                        "submitted_at": submitted_at,
                        "actor": actor,
                        "reason": reason,
                    }
            else:
                normalized = {
                    "category": category,
                    "values": values if isinstance(values, dict) else {},
                    "expected_version": expected_version,
                    "submitted_at": submitted_at,
                    "actor": actor,
                    "reason": reason,
                }
            fingerprint = json.dumps(normalized, ensure_ascii=False, sort_keys=True, default=str)
            existing = self._results.get(resolved_request)
            if existing is not None:
                if self._fingerprints.get(resolved_request) != fingerprint:
                    return self._reject_request_conflict(category, resolved_request, existing)
                replay = dict(existing)
                replay["idempotent_replay"] = True
                return self._public_outcome(replay)

            self._seq += 1
            receipt_seq = self._seq
            received_at = self._clock.now()

            if invalid is not None:
                return self._reject(
                    category,
                    normalized["values"] if isinstance(normalized["values"], dict) else {},
                    (
                        int(expected_version)
                        if isinstance(expected_version, int)
                        and not isinstance(expected_version, bool)
                        else None
                    ),
                    self._number_or_none(submitted_at),
                    str(actor) if isinstance(actor, str) else "",
                    str(reason) if isinstance(reason, str) else "",
                    resolved_request,
                    received_at,
                    receipt_seq,
                    "invalid_request",
                    invalid,
                    fingerprint,
                )

            actor_text = normalized["actor"]
            reason_text = normalized["reason"]
            expected = normalized["expected_version"]
            submitted = normalized["submitted_at"]
            candidate, rejection = self._build_candidate(category, normalized["values"])
            if candidate is None:
                return self._reject(
                    category,
                    dict(normalized["values"]),
                    expected,
                    submitted,
                    actor_text,
                    reason_text,
                    resolved_request,
                    received_at,
                    receipt_seq,
                    "invalid_values",
                    rejection or "配置取值非法",
                    fingerprint,
                )

            state = self._states[category]
            policy = CATEGORY_POLICIES[category]
            rejection_reason = self._conflict_reason(state, policy, expected, submitted, receipt_seq)
            if rejection_reason is not None:
                return self._reject(
                    category,
                    dict(normalized["values"]),
                    expected,
                    submitted,
                    actor_text,
                    reason_text,
                    resolved_request,
                    received_at,
                    receipt_seq,
                    rejection_reason[0],
                    rejection_reason[1],
                    fingerprint,
                )

            applied_values = dataclasses.asdict(getattr(candidate, category))
            new_version = state["version"] + 1
            # 同基版本的第二笔一旦按更晚时间戳覆盖第一笔，就关闭这一并发代际；
            # 此后仍带旧版本号的请求一律 stale_version，不能无限盖掉后续新值。
            committed_base_version = expected if expected == state["version"] else new_version
            outcome = self._outcome(
                category,
                True,
                dict(normalized["values"]),
                expected,
                new_version,
                submitted,
                actor_text,
                reason_text,
                resolved_request,
                received_at,
                receipt_seq,
                base_version=committed_base_version,
                request_fingerprint=fingerprint,
            )
            self._remember(resolved_request, fingerprint, outcome)
            self._publish(ACTION_ACCEPTED, "notice", f"配置 {category} 已更新", outcome)
            if apply_config is not None:
                try:
                    apply_config(candidate)
                except (ConfigError, ValueError) as error:
                    raise RuntimeError("已审计的配置应用失败") from error
            self._config = candidate
            self._states[category] = {
                "policy": policy,
                "version": outcome["current_version"],
                "base_version": committed_base_version,
                "values": dict(applied_values),
                "submitted_at": submitted,
                "received_at": received_at,
                "receipt_seq": receipt_seq,
                "actor": actor_text,
                "reason": reason_text,
                "request_id": resolved_request,
                "last_rejection": state.get("last_rejection"),
            }
            self._persist()
            return self._public_outcome(outcome)

    def _restore_request_index(self) -> None:
        """从最近的配置请求索引恢复幂等表，避免重启后误判同一请求。"""

        index = self._store.read("config_requests")
        if not isinstance(index, dict):
            return
        if isinstance(index.get("seq"), int):
            self._seq = max(self._seq, int(index["seq"]))
        requests = index.get("requests")
        if not isinstance(requests, dict):
            return
        for request_id, raw in requests.items():
            if isinstance(request_id, str) and isinstance(raw, dict) and "outcome" in raw:
                fingerprint = raw.get("fingerprint", "")
                self._remember(request_id, str(fingerprint), dict(raw["outcome"]))

    def _persist(self) -> None:
        """原子落盘当前配置状态与最近幂等结果。"""

        requests = {}
        for request_id, outcome in self._results.items():
            requests[request_id] = {
                "fingerprint": self._fingerprints.get(request_id, ""),
                "outcome": outcome,
            }
        self._store.write(
            "config_requests",
            {"seq": self._seq, "requests": requests},
        )

    def _replay(self) -> None:
        mapping = config_to_mapping(self._config)
        mapping["station"]["storage_root"] = self._config.storage_root
        for raw in self._audit.replay_from_journal():
            if raw.get("component") != "config":
                continue
            payload = dict(raw.get("payload") or {})
            category = payload.get("category")
            if not isinstance(category, str) or category not in CATEGORY_POLICIES:
                continue
            action = raw.get("action")
            request_id = payload.get("request_id")
            if action == ACTION_ACCEPTED:
                values = payload.get("values")
                version = payload.get("current_version")
                if isinstance(values, dict) and isinstance(version, int):
                    mapping["limits"][category].update(values)
                    self._config = StationConfig.from_mapping(mapping)
                    self._states[category] = {
                        "policy": CATEGORY_POLICIES[category],
                        "version": int(version),
                        "base_version": int(payload.get("base_version", version - 1)),
                        "values": dict(config_to_mapping(self._config)["limits"][category]),
                        "submitted_at": self._number_or_none(payload.get("submitted_at")),
                        "received_at": self._number_or_none(payload.get("received_at")),
                        "receipt_seq": (
                            payload.get("receipt_seq")
                            if isinstance(payload.get("receipt_seq"), int)
                            else None
                        ),
                        "actor": str(payload.get("actor", "")),
                        "reason": str(payload.get("reason", "")),
                        "request_id": str(request_id or ""),
                        "last_rejection": None,
                    }
                    self._seq = max(self._seq, self._states[category]["receipt_seq"] or 0)
                if isinstance(request_id, str):
                    result = self._outcome_from_payload(payload, True)
                    self._remember(request_id, str(payload.get("request_fingerprint", "")), result)
            elif action == ACTION_REJECTED:
                outcome = self._outcome_from_payload(payload, False)
                self._states[category]["last_rejection"] = outcome
                if isinstance(request_id, str):
                    self._remember(
                        request_id,
                        str(payload.get("request_fingerprint", "")),
                        outcome,
                    )

    def _initial_state(self, category: str) -> dict:
        return {
            "policy": CATEGORY_POLICIES[category],
            "version": 0,
            "base_version": 0,
            "values": dict(config_to_mapping(self._config)["limits"][category]),
            "submitted_at": None,
            "received_at": None,
            "receipt_seq": None,
            "actor": None,
            "reason": None,
            "request_id": None,
            "last_rejection": None,
        }

    def _state_dict(self, category: str) -> dict:
        state = self._states[category]
        return {
            "category": category,
            "policy": state["policy"],
            "version": state["version"],
            "base_version": state["base_version"],
            "values": dict(state["values"]),
            "last_accepted": self._last_change(state),
            "last_rejection": (
                self._public_outcome(state["last_rejection"])
                if state.get("last_rejection")
                else None
            ),
        }

    def _last_change(self, state: dict) -> dict | None:
        if state["request_id"] is None:
            return None
        return {
            "version": state["version"],
            "base_version": state["base_version"],
            "submitted_at": state["submitted_at"],
            "received_at": state["received_at"],
            "receipt_seq": state["receipt_seq"],
            "actor": state["actor"],
            "reason": state["reason"],
            "request_id": state["request_id"],
        }

    def _normalized_request(
        self,
        category: str,
        values: dict,
        expected_version: int,
        submitted_at: float,
        actor: str,
        reason: str,
    ) -> dict:
        normalized_values: dict[str, Any] = {}
        for key, value in values.items():
            key_text = str(key)
            if key_text == "max_waiting":
                normalized_values[key_text] = int(value)
            elif isinstance(value, bool):
                normalized_values[key_text] = value
            else:
                normalized_values[key_text] = float(value)
        return {
            "category": category,
            "values": normalized_values,
            "expected_version": int(expected_version),
            "submitted_at": float(submitted_at),
            "actor": actor.strip(),
            "reason": reason.strip(),
        }

    def _validate_request(
        self,
        values: Any,
        expected_version: Any,
        submitted_at: Any,
        actor: Any,
        reason: Any,
    ) -> str | None:
        if not isinstance(values, dict) or not values:
            return "values 必须是非空补丁映射"
        if (
            isinstance(expected_version, bool)
            or not isinstance(expected_version, int)
            or expected_version < 0
        ):
            return "expected_version 必须是非负整数"
        if (
            isinstance(submitted_at, bool)
            or not isinstance(submitted_at, (int, float))
            or not math.isfinite(float(submitted_at))
        ):
            return "submitted_at 必须是有限数值时间戳"
        if not isinstance(actor, str) or not actor.strip():
            return "actor 不能为空"
        if not isinstance(reason, str) or not reason.strip():
            return "reason 不能为空"
        return None

    def _build_candidate(self, category: str, values: dict) -> tuple[StationConfig | None, str | None]:
        section_class = _CATEGORY_CLASSES[category]
        allowed = {field.name for field in dataclasses.fields(section_class)}
        unknown = sorted(set(values) - allowed)
        if unknown:
            return None, f"未知配置字段: {', '.join(unknown)}"
        mapping = config_to_mapping(self._config)
        mapping["station"]["storage_root"] = self._config.storage_root
        mapping["limits"][category].update(values)
        try:
            return StationConfig.from_mapping(mapping), None
        except ConfigError as error:
            return None, str(error)

    def _conflict_reason(
        self,
        state: dict,
        policy: str,
        expected: int,
        submitted_at: float,
        receipt_seq: int,
    ) -> tuple[str, str] | None:
        current_version = state["version"]
        if expected == current_version:
            return None
        if expected > current_version:
            return (
                "future_version",
                f"期望版本 {expected} 高于当前版本 {current_version}",
            )
        if policy == FIRST_WINS:
            return (
                "stale_version",
                f"first_wins 类别只接受当前版本；期望版本 {expected} 已过期，当前版本 {current_version}",
            )
        if state["request_id"] is None:
            return ("stale_version", f"期望版本 {expected} 已过期，当前版本 {current_version}")
        if expected < state["base_version"]:
            return (
                "stale_version",
                f"并发代际已由版本 {state['base_version']} 关闭，期望版本 {expected} 已过期",
            )
        current_tuple = (state["submitted_at"], state["receipt_seq"])
        if (submitted_at, receipt_seq) < current_tuple:
            return (
                "stale_timestamp",
                f"提交时间戳 {submitted_at} 早于已采纳的 {state['submitted_at']}",
            )
        return None

    def _reject(
        self,
        category: str,
        values: dict,
        expected: int | None,
        submitted_at: float | None,
        actor: str,
        reason: str,
        request_id: str,
        received_at: float,
        receipt_seq: int,
        rejection_reason: str,
        message: str,
        fingerprint: str = "",
    ) -> dict:
        outcome = self._outcome(
            category,
            False,
            values,
            expected if expected is not None else -1,
            self._states[category]["version"],
            submitted_at if submitted_at is not None else 0.0,
            actor,
            reason,
            request_id,
            received_at,
            receipt_seq,
            rejection_reason=rejection_reason,
            message=message,
            winning_request_id=self._states[category].get("request_id"),
            winning_submitted_at=self._states[category].get("submitted_at"),
            request_fingerprint=fingerprint,
        )
        self._remember(request_id, fingerprint, outcome)
        self._publish(ACTION_REJECTED, "warning", message, outcome)
        self._states[category]["last_rejection"] = dict(outcome)
        self._persist()
        return self._public_outcome(outcome)

    def _reject_request_conflict(self, category: str, request_id: str, existing: dict) -> dict:
        self._seq += 1
        outcome = {
            "accepted": False,
            "status": "rejected",
            "category": category,
            "policy": CATEGORY_POLICIES[category],
            "request_id": request_id,
            "current_version": self._states[category]["version"],
            "rejection_reason": "request_id_conflict",
            "message": "同一 request_id 对应不同请求内容",
            "original_status": existing.get("status"),
            "original_accepted": existing.get("accepted"),
        }
        self._publish(
            ACTION_REQUEST_CONFLICT,
            "warning",
            outcome["message"],
            {**outcome, "station": self._unit},
        )
        return dict(outcome)

    def _outcome(
        self,
        category: str,
        accepted: bool,
        values: dict,
        expected_version: int,
        current_version: int,
        submitted_at: float,
        actor: str,
        reason: str,
        request_id: str,
        received_at: float,
        receipt_seq: int,
        *,
        base_version: int | None = None,
        rejection_reason: str | None = None,
        message: str = "",
        winning_request_id: str | None = None,
        winning_submitted_at: float | None = None,
        request_fingerprint: str = "",
    ) -> dict:
        outcome: dict[str, Any] = {
            "accepted": accepted,
            "status": "accepted" if accepted else "rejected",
            "category": category,
            "policy": CATEGORY_POLICIES[category],
            "values": dict(values),
            "expected_version": expected_version,
            "current_version": current_version,
            "submitted_at": submitted_at,
            "received_at": received_at,
            "receipt_seq": receipt_seq,
            "actor": actor,
            "reason": reason,
            "request_id": request_id,
        }
        if base_version is not None:
            outcome["base_version"] = base_version
        if rejection_reason is not None:
            outcome["rejection_reason"] = rejection_reason
            outcome["message"] = message
            outcome["winning_request_id"] = winning_request_id
            outcome["winning_submitted_at"] = winning_submitted_at
        if request_fingerprint:
            outcome["request_fingerprint"] = request_fingerprint
        return outcome

    def _outcome_from_payload(self, payload: dict, accepted: bool) -> dict:
        keys = (
            "accepted",
            "status",
            "category",
            "policy",
            "values",
            "expected_version",
            "current_version",
            "submitted_at",
            "received_at",
            "receipt_seq",
            "actor",
            "reason",
            "request_id",
            "base_version",
            "rejection_reason",
            "message",
            "winning_request_id",
            "winning_submitted_at",
            "request_fingerprint",
        )
        outcome = {key: payload[key] for key in keys if key in payload}
        outcome["accepted"] = accepted
        outcome["status"] = "accepted" if accepted else "rejected"
        return outcome

    def _publish(self, action: str, severity: str, message: str, payload: dict) -> None:
        fields = dict(payload)
        fields.pop("message", None)
        fields.pop("station", None)
        fields = {key: value for key, value in fields.items() if value is not None}
        self._bus.publish(
            Event.of(
                "config",
                "config",
                action,
                station=self._unit,
                severity=severity,
                message=message if isinstance(message, str) else str(fields.get("message", "")),
                **fields,
            )
        )

    def _public_outcome(self, outcome: dict) -> dict:
        """返回对控制台可见的结论，内部幂等指纹只落审计不返回。"""

        public = dict(outcome)
        public.pop("request_fingerprint", None)
        return public

    def _remember(self, request_id: str, fingerprint: str, outcome: dict) -> None:
        self._results[request_id] = dict(outcome)
        self._fingerprints[request_id] = fingerprint
        if len(self._results) > 4096:
            stale_ids = sorted(
                self._results,
                key=lambda key: (
                    self._results[key].get("receipt_seq") is None,
                    self._results[key].get("receipt_seq", 0),
                ),
            )[:-4096]
            for stale_id in stale_ids:
                self._results.pop(stale_id, None)
                self._fingerprints.pop(stale_id, None)

    @staticmethod
    def _number_or_none(value: Any) -> float | None:
        if isinstance(value, bool) or not isinstance(value, (int, float)):
            return None
        return float(value)
