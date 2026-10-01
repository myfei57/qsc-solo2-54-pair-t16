"""运行期限值配置的并发、幂等、审计与重启恢复测试。"""

from __future__ import annotations

import threading

from hydrorefuel.config import default_config
from hydrorefuel.app import build_platform
from hydrorefuel.config_manager import FIRST_WINS, LAST_COMMIT_TS


def _submit(platform, category, values, request_id, *, expected_version=0, submitted_at=100.0):
    return platform.change_config(
        category,
        values,
        expected_version=expected_version,
        submitted_at=submitted_at,
        actor="operator-a",
        reason="工艺调整",
        request_id=request_id,
    )


def test_first_wins_accepts_only_one_same_version_change(platform):
    barrier = threading.Barrier(2)
    outcomes = []
    outcomes_lock = threading.Lock()

    def worker(request_id: str, threshold_ppm: float) -> None:
        barrier.wait()
        outcome = _submit(
            platform,
            "leak",
            {"threshold_ppm": threshold_ppm},
            request_id,
            submitted_at=100.0,
        )
        with outcomes_lock:
            outcomes.append(outcome)

    threads = [
        threading.Thread(target=worker, args=("req-leak-1", 4100.0)),
        threading.Thread(target=worker, args=("req-leak-2", 4200.0)),
    ]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join()

    assert sorted(item["accepted"] for item in outcomes) == [False, True]
    assert "request_fingerprint" not in outcomes[0]
    assert platform.leak.limits.threshold_ppm in (4100.0, 4200.0)
    status = platform.config_status()["categories"]["leak"]
    assert status["policy"] == FIRST_WINS
    assert status["version"] == 1
    assert status["last_rejection"]["rejection_reason"] == "stale_version"
    audit_actions = [
        entry["action"]
        for entry in platform.audit.entries()
        if entry["component"] == "config"
    ]
    assert audit_actions.count("config_change_accepted") == 1
    assert audit_actions.count("config_change_rejected") == 1
    accepted_audit = next(
        entry
        for entry in platform.audit.replay_from_journal()
        if entry["action"] == "config_change_accepted"
    )
    assert accepted_audit["payload"]["request_fingerprint"]
    assert status["last_rejection"]["values"]["threshold_ppm"] in (4100.0, 4200.0)


def test_first_wins_stale_request_is_idempotent_and_does_not_apply(platform):
    accepted = _submit(platform, "leak", {"threshold_ppm": 4100.0}, "accepted", submitted_at=100.0)
    before = platform.audit.summary()["total"]

    rejected = _submit(platform, "leak", {"threshold_ppm": 3000.0}, "stale", submitted_at=101.0)
    replay = _submit(platform, "leak", {"threshold_ppm": 3000.0}, "stale", submitted_at=101.0)
    after = platform.audit.summary()["total"]

    assert accepted["accepted"] is True
    assert rejected["accepted"] is False
    assert rejected["rejection_reason"] == "stale_version"
    assert replay["accepted"] is False
    assert replay is not rejected
    assert replay["idempotent_replay"] is True
    assert replay["rejection_reason"] == "stale_version"
    assert platform.leak.limits.threshold_ppm == 4100.0
    assert after == before + 1


def test_last_commit_ts_takes_latest_timestamp_for_same_generation(platform):
    newer = _submit(
        platform,
        "flow",
        {"max_rate_kg_per_min": 4.2},
        "flow-new",
        submitted_at=200.0,
    )
    older = _submit(
        platform,
        "flow",
        {"max_rate_kg_per_min": 3.2},
        "flow-old",
        submitted_at=100.0,
    )

    assert newer["accepted"] is True
    assert older["accepted"] is False
    assert older["rejection_reason"] == "stale_timestamp"
    assert older["winning_request_id"] == "flow-new"
    status = platform.config_status()["categories"]["flow"]
    assert status["policy"] == LAST_COMMIT_TS
    assert status["version"] == 1
    assert status["values"]["max_rate_kg_per_min"] == 4.2
    assert platform.meter.limits.max_rate_kg_per_min == 4.2

    replay = _submit(
        platform,
        "flow",
        {"max_rate_kg_per_min": 3.2},
        "flow-old",
        submitted_at=100.0,
    )
    assert replay["idempotent_replay"] is True
    assert replay["accepted"] is False
    assert platform.meter.limits.max_rate_kg_per_min == 4.2


def test_last_commit_ts_closes_generation_after_one_override(platform):
    platform.change_config(
        "flow",
        {"max_rate_kg_per_min": 4.0},
        expected_version=0,
        submitted_at=100.0,
        actor="operator-a",
        reason="调整",
        request_id="first",
    )
    platform.change_config(
        "flow",
        {"max_rate_kg_per_min": 4.2},
        expected_version=0,
        submitted_at=200.0,
        actor="operator-a",
        reason="调整",
        request_id="override",
    )
    tail = platform.change_config(
        "flow",
        {"max_rate_kg_per_min": 5.0},
        expected_version=0,
        submitted_at=300.0,
        actor="operator-a",
        reason="调整",
        request_id="closed-generation",
    )

    assert tail["accepted"] is False
    assert tail["rejection_reason"] == "stale_version"
    assert platform.meter.limits.max_rate_kg_per_min == 4.2
    assert platform.config_status()["categories"]["flow"]["version"] == 2


def test_last_commit_ts_breaks_equal_timestamp_by_server_receipt_order(platform):
    first = _submit(
        platform,
        "flow",
        {"max_rate_kg_per_min": 3.9},
        "equal-ts-1",
        submitted_at=100.0,
    )
    second = _submit(
        platform,
        "flow",
        {"max_rate_kg_per_min": 4.0},
        "equal-ts-2",
        submitted_at=100.0,
    )

    assert first["accepted"] is True
    assert second["accepted"] is True
    assert second["current_version"] == 2
    assert platform.meter.limits.max_rate_kg_per_min == 4.0


def test_rejected_request_remains_idempotent_after_restart(tmp_path, clock):
    root = str(tmp_path / "state")
    first = build_platform(default_config(), clock=clock, storage_root=root)
    first.change_config(
        "flow",
        {"max_rate_kg_per_min": 4.0},
        expected_version=0,
        submitted_at=200.0,
        actor="operator-a",
        reason="现场流量调整",
        request_id="new",
    )
    first.change_config(
        "flow",
        {"max_rate_kg_per_min": 3.0},
        expected_version=0,
        submitted_at=100.0,
        actor="operator-a",
        reason="现场流量调整",
        request_id="old",
    )

    second = build_platform(default_config(), clock=clock, storage_root=root)
    replay = second.change_config(
        "flow",
        {"max_rate_kg_per_min": 3.0},
        expected_version=0,
        submitted_at=100.0,
        actor="operator-a",
        reason="现场流量调整",
        request_id="old",
    )
    assert replay["accepted"] is False
    assert replay["idempotent_replay"] is True
    assert second.config_status()["categories"]["flow"]["last_rejection"]["request_id"] == "old"


def test_invalid_values_are_rejected_audited_and_leave_config_unchanged(platform):
    before = platform.leak.limits.threshold_ppm
    outcome = _submit(platform, "leak", {"threshold_ppm": 0.5}, "invalid", submitted_at=100.0)

    assert outcome["accepted"] is False
    assert outcome["rejection_reason"] == "invalid_values"
    assert platform.leak.limits.threshold_ppm == before
    status = platform.config_status()["categories"]["leak"]
    assert status["last_rejection"]["request_id"] == "invalid"
    assert status["last_rejection"]["rejection_reason"] == "invalid_values"


def test_request_id_replay_with_different_payload_is_conflict(platform):
    _submit(platform, "leak", {"threshold_ppm": 4100.0}, "same-id", submitted_at=100.0)
    conflict = _submit(platform, "leak", {"threshold_ppm": 4200.0}, "same-id", submitted_at=101.0)

    assert conflict["accepted"] is False
    assert conflict["rejection_reason"] == "request_id_conflict"
    assert platform.leak.limits.threshold_ppm == 4100.0


def test_accepted_config_is_restored_from_audit_after_restart(tmp_path, clock):
    root = str(tmp_path / "state")
    first = build_platform(default_config(), clock=clock, storage_root=root)
    outcome = first.change_config(
        "flow",
        {"max_rate_kg_per_min": 4.1},
        expected_version=0,
        submitted_at=100.0,
        actor="operator-a",
        reason="现场流量调整",
        request_id="restart-1",
    )
    assert outcome["accepted"] is True

    second = build_platform(default_config(), clock=clock, storage_root=root)
    status = second.config_status()["categories"]["flow"]
    assert status["version"] == 1
    assert status["values"]["max_rate_kg_per_min"] == 4.1
    assert second.meter.limits.max_rate_kg_per_min == 4.1
    replayed = second.change_config(
        "flow",
        {"max_rate_kg_per_min": 4.1},
        expected_version=0,
        submitted_at=100.0,
        actor="operator-a",
        reason="现场流量调整",
        request_id="restart-1",
    )
    assert replayed["accepted"] is True
    assert replayed["idempotent_replay"] is True
