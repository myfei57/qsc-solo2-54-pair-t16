"""预冷组件。

高压加注前必须把氢气冷到目标温度并保持一段时间，否则枪口温升会触发跳枪。
:class:`TemperatureModel` 按冷速降温，:class:`Precooler` 记录是否已经到达
允许带并保持足够时长，编排据此决定是否允许开加注阀。
"""

from __future__ import annotations

from .precool import Precooler
from .snapshot import CoolSnapshot
from .temperature import TemperatureModel

__all__ = ["Precooler", "TemperatureModel", "CoolSnapshot"]
