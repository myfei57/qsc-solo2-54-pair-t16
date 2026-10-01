"""控制台配置展示与提交接口测试。"""

from __future__ import annotations

from hydrorefuel.console.api import Api


def _body(request_id: str, *, submitted_at: float = 100.0, expected_version: int = 0):
    return {
        "values": {"threshold_ppm": 4100.0},
        "expected_version": expected_version,
        "submitted_at": submitted_at,
        "actor": "operator-a",
        "reason": "限值调整",
        "request_id": request_id,
    }


def test_config_status_is_displayable(platform):
    api = Api(platform)

    status_code, payload = api.handle("GET", "/api/config", {}, {})

    assert status_code == 200
    assert payload["categories"]["leak"]["version"] == 0
    assert payload["categories"]["leak"]["policy"] == "first_wins"
    assert payload["config"]["limits"]["leak"]["threshold_ppm"] == 4000.0

    status_code, category = api.handle("GET", "/api/config/leak", {}, {})
    assert status_code == 200
    assert category["category"]["category"] == "leak"


def test_console_accepts_then_rejects_and_replays_stale_config(platform):
    api = Api(platform)

    accepted_code, accepted = api.handle("POST", "/api/config/leak", {}, _body("console-1"))
    stale_code, stale = api.handle("POST", "/api/config/leak", {}, _body("console-2"))
    replay_code, replay = api.handle("POST", "/api/config/leak", {}, _body("console-2"))

    assert accepted_code == 200
    assert accepted["accepted"] is True
    assert stale_code == 409
    assert stale["rejection_reason"] == "stale_version"
    assert replay_code == 409
    assert replay["idempotent_replay"] is True

    _, status = api.handle("GET", "/api/config/leak", {}, {})
    assert status["category"]["version"] == 1
    assert status["category"]["last_rejection"]["request_id"] == "console-2"

    _, audit = api.handle("GET", "/api/audit", {"limit": "10"}, {})
    actions = [entry["action"] for entry in audit["entries"]]
    assert "config_change_accepted" in actions
    assert "config_change_rejected" in actions


def test_console_rejects_missing_config_fields_without_changing_value(platform):
    api = Api(platform)

    status_code, payload = api.handle(
        "POST",
        "/api/config/leak",
        {},
        {"values": {"threshold_ppm": 4100.0}},
    )

    assert status_code == 400
    assert payload["rejection_reason"] == "invalid_request"
    assert platform.leak.limits.threshold_ppm == 4000.0
