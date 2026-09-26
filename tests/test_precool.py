"""预冷温度模型与保持计时。"""

from __future__ import annotations

from hydrorefuel.config import default_config
from hydrorefuel.cool.precool import Precooler
from hydrorefuel.cool.temperature import TemperatureModel


def test_temperature_reaches_target():
    limits = default_config().cool
    model = TemperatureModel(limits)
    for _ in range(400):
        model.cool(1.0)
    assert model.reached()
    assert model.value_c == limits.target_temp_c


def test_precool_requires_hold_time():
    limits = default_config().cool
    model = TemperatureModel(limits)
    precooler = Precooler(limits)
    precooler.start()
    for _ in range(400):
        model.cool(1.0)
        if precooler.tick(1.0, model.value_c):
            break
    assert precooler.is_ready()
    assert precooler.held_s >= limits.precool_hold_s
    assert precooler.reset() is True


def test_hold_resets_when_temperature_leaves_band():
    limits = default_config().cool
    precooler = Precooler(limits)
    precooler.start()
    precooler.tick(5.0, limits.target_temp_c)
    assert precooler.held_s == 5.0
    precooler.tick(5.0, limits.target_temp_c + 10.0)
    assert precooler.held_s == 0.0
