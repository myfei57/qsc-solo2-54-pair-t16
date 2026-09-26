"""平台统一异常类型。

现场必须区分几类失败：联锁条件不满足（运行期可恢复，条件满足即可继续）、
压力或温度越限（设备保护动作，必须重新建立工况）、流量与泄漏异常（安全
相关，必须保持闩锁直到人工复位）、以及配置或持久化失败（装配期就要拦下的
接线问题）。审计日志按异常类型分别落盘，巡检时才能一眼区分问题性质。
"""

from __future__ import annotations


class HydroError(Exception):
    """所有平台异常的基类，携带出错的组件名。"""

    def __init__(self, message: str, *, component: str = "hydrorefuel") -> None:
        super().__init__(message)
        self.message = message
        self.component = component

    def as_record(self) -> dict:
        """转成审计日志可以直接落盘的一条记录。"""

        return {
            "type": type(self).__name__,
            "component": self.component,
            "message": self.message,
        }


class InterlockError(HydroError):
    """顺序或联锁条件不满足，动作被拒绝。"""


class PressureError(HydroError):
    """压力越限或未落到目标带。"""


class FlowError(HydroError):
    """质量流量阶梯核对未通过。"""


class LeakError(HydroError):
    """泄漏检测达到阈值，闩锁保持。"""


class StorageError(HydroError):
    """持久化读写失败。"""


class ConfigError(HydroError):
    """配置缺失或取值非法。"""


class NamespaceError(HydroError):
    """命名空间重复注册或解析失败。"""
