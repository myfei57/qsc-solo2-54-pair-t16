"""端到端顺序编排。"""

from __future__ import annotations

from support import load_station


def test_full_chain_runs_in_order(platform):
    platform.start()
    load_station(platform)
    fill = platform.fill(vehicle="vehicle01", rate_kg_per_min=3.0, steps=3)
    assert fill["ok"], fill["violations"]
    stop = platform.stop_fill()
    assert stop["ok"], stop["violations"]
    assert [step["action"] for step in stop["steps"]] == ["isolate", "stop", "unseat_nozzle"]
    cycle = platform.cycle()
    assert cycle["cycle"] == 1
    assert platform.dispenser.state == "stopped"
    assert not platform.nozzle.is_seated()


def test_fill_leaves_dispenser_filling_until_stop(platform):
    platform.start()
    load_station(platform)
    platform.fill(steps=1)
    assert platform.dispenser.is_filling()
    assert platform.nozzle.is_seated()
    platform.stop_fill()
    assert platform.dispenser.state == "stopped"


def test_flow_step_mismatch_aborts_fill(platform):
    platform.start()
    load_station(platform)
    fill = platform.fill(steps=1, rate_kg_per_min=3.0, dt=30.0)
    assert not fill["ok"]
    assert "flow_step_1_mismatch" in fill["violations"]
    assert platform.dispenser.fill_valve_open() is False
    assert not platform.nozzle.is_seated()


def test_precool_happens_before_fill_valve(platform):
    platform.start()
    load_station(platform)
    report = platform.fill(steps=1)
    actions = [step["action"] for step in report["steps"]]
    assert actions.index("precool") < actions.index("open_fill_valve")
