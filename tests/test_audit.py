"""审计留存、事件流与回放。"""

from __future__ import annotations

from hydrorefuel.audit.record import AuditRecord
from hydrorefuel.audit.report import summarize
from hydrorefuel.audit.timeline import build_timeline
from hydrorefuel.errors import InterlockError


def test_events_are_recorded_as_audit(platform):
    platform.start()
    platform.unload(target_kg=10.0)
    entries = platform.audit.entries()
    assert entries
    assert any(entry["action"] == "unload_complete" for entry in entries)
    assert platform.audit.summary()["total"] >= 1


def test_rejections_show_up_as_alarms(platform):
    platform.start()
    platform.stop_fill()
    alarms = platform.audit.alarms()
    assert any(item["severity"] == "alarm" for item in alarms)
    timeline = build_timeline(platform.audit.records(), station=platform.unit)
    assert timeline[0]["step"] == 1


def test_error_records_carry_component(platform):
    record = platform.note_error(InterlockError("拒绝", component="vent"))
    assert record["component"] == "vent"
    assert summarize([AuditRecord.from_dict(record)])["by_component"]["vent"] == 1


def test_journal_replay(platform):
    platform.start()
    platform.cycle()
    assert platform.audit.replay_segment(0)
    assert platform.audit.replay_from_journal()
