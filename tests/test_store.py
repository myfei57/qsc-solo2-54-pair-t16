"""文件型持久化。"""

from __future__ import annotations

from hydrorefuel.store.journal import JsonlJournal
from hydrorefuel.store.jsonfile import JsonStore


def test_json_store_roundtrip(tmp_path):
    store = JsonStore(str(tmp_path / "state"))
    path = store.write("platform_state", {"operations": 2})
    assert store.exists("platform_state")
    assert store.read("platform_state") == {"operations": 2}
    assert store.path_of("platform_state") == path
    assert store.list_ids() == ["platform_state"]
    assert store.remove("platform_state") is True
    assert store.read("platform_state") is None
    assert store.remove("platform_state") is False


def test_journal_rolls_segments(tmp_path):
    journal = JsonlJournal(str(tmp_path / "state"), "audit", segment_limit=2)
    journal.append({"i": 0})
    journal.append({"i": 1})
    journal.append({"i": 2})
    assert journal.count() == 3
    assert journal.topic == "audit"
    assert journal.active_segment() == 1
    assert len(journal.segments()) == 2
    assert journal.read_segment(0) == [{"i": 0}, {"i": 1}]
    assert journal.read_all()[-1] == {"i": 2}
