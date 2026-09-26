"""配置解析与校验。"""

from __future__ import annotations

from pathlib import Path

import pytest

from hydrorefuel.config import (
    CompressorLimits,
    FlowLimits,
    StationConfig,
    config_to_mapping,
    default_config,
    load_config,
)
from hydrorefuel.errors import ConfigError

ROOT = Path(__file__).resolve().parents[1]


def test_repository_config_matches_defaults():
    loaded = load_config(str(ROOT / "config" / "hydrorefuel.json"))
    assert loaded == default_config()


def test_config_round_trips_through_mapping():
    cfg = default_config()
    assert StationConfig.from_mapping(config_to_mapping(cfg)) == cfg


def test_missing_limits_section_is_rejected():
    with pytest.raises(ConfigError):
        StationConfig.from_mapping({"station": {"name": "x", "storage_root": "y"}})


def test_invalid_limits_are_rejected():
    with pytest.raises(ConfigError):
        CompressorLimits.from_mapping(
            {
                "inlet_min_mpa": 10.0,
                "outlet_target_mpa": 5.0,
                "ramp_mpa_per_s": 1.0,
                "surge_band_mpa": 1.0,
                "min_flow_kg_per_min": 1.0,
            }
        )
    with pytest.raises(ConfigError):
        FlowLimits.from_mapping(
            {
                "step_target_kg": 1.0,
                "step_tolerance_kg": 2.0,
                "max_rate_kg_per_min": 3.0,
                "min_rate_kg_per_min": 0.5,
            }
        )


def test_missing_file_is_rejected():
    with pytest.raises(ConfigError):
        load_config(str(ROOT / "config" / "missing.json"))
