"""配置变更并发仲裁、幂等与审计。"""

from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor

from hydrorefuel.app import build_platform
from hydrorefuel.config import default_config


def _request(
    request_id: str,
    category: str,
    values: dict,
    *,
    expected_version: int = 0,
    submitted_at: float = 1.0,
    actor: str = "alice",
    reason: str = "调整限值",
) -> dict:
    return {
        "request_id": request_id,
        "category": category,
        "values": values,
        "expected_version": expected_version,
        "submitted_at": submitted_at,
        "actor": actor,
        "reason": reason,
    }


def test_first_writer_wins_category_keeps_first_valid_submission(platform):
    first = platform.submit_config_change(
        _request("r1", "leak", {"threshold_ppm": 4500.0}, submitted_at=10.0)
    )
    stale = platform.submit_config_change(
        _request("r2", "leak", {"threshold_ppm": 4100.0}, expected_version=0, submitted_at=20.0)
    )

    assert first["accepted"] is True
    assert first["version"] == 1
    assert stale["accepted"] is False
    assert stale["reject_code"] == "stale_version"
    assert platform.config.leak.threshold_ppm == 4500.0
    assert platform.leak_snapshot()["threshold_ppm"] == 4500.0
    assert platform.config_snapshot()["categories"]["leak"]["request_id"] == "r1"


def test_first_writer_rejected_request_is_idempotent(platform):
    platform.submit_config_change(_request("r1", "truck", {"vent_timeout_s": 100.0}))
    rejected_once = platform.submit_config_change(_request("r2", "truck", {"vent_timeout_s": 120.0}))
    rejected_twice = platform.submit_config_change(_request("r2", "truck", {"vent_timeout_s": 120.0}))

    assert rejected_once["status"] == "rejected"
    assert rejected_twice["status"] == "rejected"
    assert rejected_twice["idempotent"] is True
    assert rejected_twice == {**rejected_once, "idempotent": True}
    config_actions = [
        entry for entry in platform.audit.entries()
        if entry["payload"].get("request_id") == "r2"
    ]
    assert len(config_actions) == 1


def test_last_timestamp_wins_category_rejects_older_timestamp(platform):
    newer = platform.submit_config_change(
        _request("newer", "buffer", {"target_pressure_mpa": 43.0}, submitted_at=20.0)
    )
    older = platform.submit_config_change(
        _request(
            "older",
            "buffer",
            {"target_pressure_mpa": 44.0},
            expected_version=0,
            submitted_at=10.0,
        )
    )

    assert newer["accepted"] is True
    assert older["accepted"] is False
    assert older["reject_code"] == "stale_timestamp"
    assert platform.config.buffer.target_pressure_mpa == 43.0


def test_last_timestamp_wins_accepts_newer_timestamp_after_conflict(platform):
    first = platform.submit_config_change(
        _request("first", "cool", {"target_temp_c": -38.0}, submitted_at=10.0)
    )
    second = platform.submit_config_change(
        _request(
            "second",
            "cool",
            {"target_temp_c": -42.0},
            expected_version=0,
            submitted_at=20.0,
        )
    )

    assert first["version"] == 1
    assert second["accepted"] is True
    assert second["version"] == 2
    assert platform.config.cool.target_temp_c == -42.0


def test_last_timestamp_policy_requires_explicit_submitted_at(platform):
    request = _request("no-ts", "buffer", {"target_pressure_mpa": 43.0})
    del request["submitted_at"]

    outcome = platform.submit_config_change(request)

    assert outcome["status"] == "invalid"
    assert outcome["reject_reason"] == "最后时间戳策略必须显式提交 submitted_at"


def test_stale_lww_request_is_rejected_before_candidate_validation(platform):
    platform.submit_config_change(
        _request("newer", "buffer", {"target_pressure_mpa": 43.0}, submitted_at=20.0)
    )
    outcome = platform.submit_config_change(
        _request(
            "older-invalid",
            "buffer",
            {"target_pressure_mpa": -1.0},
            expected_version=0,
            submitted_at=10.0,
        )
    )

    assert outcome["reject_code"] == "stale_timestamp"
    assert platform.config.buffer.target_pressure_mpa == 43.0


def test_same_timestamp_does_not_apply_twice(platform):
    first = platform.submit_config_change(
        _request("first", "buffer", {"target_pressure_mpa": 43.0}, submitted_at=10.0)
    )
    tie = platform.submit_config_change(
        _request(
            "tie",
            "buffer",
            {"target_pressure_mpa": 44.0},
            expected_version=0,
            submitted_at=10.0,
        )
    )

    assert first["accepted"] is True
    assert tie["accepted"] is False
    assert tie["reject_code"] == "stale_timestamp"


def test_concurrent_same_key_has_one_application(platform):
    def attempt(item: tuple[int, str]) -> dict:
        index, actor = item
        return platform.submit_config_change(
            _request(
                f"r-{index}",
                "leak",
                {"threshold_ppm": 4000.0 + index},
                expected_version=0,
                submitted_at=float(index),
                actor=actor,
            )
        )

    with ThreadPoolExecutor(max_workers=8) as pool:
        outcomes = list(pool.map(attempt, [(i, f"user{i}") for i in range(16)]))

    assert sum(item["accepted"] for item in outcomes) == 1
    assert platform.config_snapshot()["categories"]["leak"]["version"] == 1
    accepted_ids = [item["request_id"] for item in outcomes if item["accepted"]]
    assert len(accepted_ids) == 1
    applied = [
        entry
        for entry in platform.audit.entries()
        if entry["action"] == "config_change_applied"
    ]
    assert len(applied) == 1
    assert applied[0]["payload"]["request_id"] == accepted_ids[0]


def test_invalid_candidate_is_rejected_before_applying(platform):
    outcome = platform.submit_config_change(
        _request("bad", "comp", {"inlet_min_mpa": 100.0}, submitted_at=1.0)
    )

    assert outcome["accepted"] is False
    assert outcome["status"] == "invalid"
    assert outcome["reject_code"] == "invalid_request"
    assert platform.config.compressor.inlet_min_mpa == default_config().compressor.inlet_min_mpa


def test_restored_manager_keeps_version_and_idempotency(tmp_path, clock):
    storage = str(tmp_path / "state")
    first = build_platform(default_config(), clock=clock, storage_root=storage)
    first.submit_config_change(_request("r1", "leak", {"threshold_ppm": 4500.0}))
    first.submit_config_change(_request("r2", "leak", {"threshold_ppm": 4100.0}))

    restored = build_platform(default_config(), clock=clock, storage_root=storage)
    replayed = restored.submit_config_change(_request("r2", "leak", {"threshold_ppm": 4100.0}))

    assert restored.config.leak.threshold_ppm == 4500.0
    assert restored.config_snapshot()["categories"]["leak"]["version"] == 1
    assert replayed["idempotent"] is True
    assert replayed["accepted"] is False
