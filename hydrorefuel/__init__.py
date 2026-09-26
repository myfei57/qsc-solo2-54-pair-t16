"""加氢站卸氢增压与加注顺序控制服务。

对外只暴露装配入口 ``Platform`` 与工厂 ``build_platform``。各组件包
（truck、vent、comp、buffer、cool、flow、disp、leak、queue、ns、store、
audit、sequence、console）由 ``Platform`` 的真实调用链串联：组件之间不互相
导入对方的私有实现，只依赖对方暴露的状态查询与动作接口。
"""

from __future__ import annotations

__version__ = "1.0.0"

from .app import Platform, build_platform

__all__ = ["Platform", "build_platform", "__version__"]
