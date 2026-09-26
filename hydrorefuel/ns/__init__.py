"""现场命名空间与工艺链拓扑。

命名空间把"区域.设备"映射到设备类型，控制台与审计共用同一套名字；拓扑描述
「槽车卸氢 → 压缩机增压 → 瓶组缓存 → 预冷加注 → 放散 → 审计」这条硬顺序
链，用来在操作前检查工位是否满足前一阶段已完成。
"""

from __future__ import annotations

from .registry import Device, NamespaceRegistry
from .topology import STAGES, Stage, Topology, build_default_topology

__all__ = ["Device", "NamespaceRegistry", "Stage", "Topology", "STAGES", "build_default_topology"]
