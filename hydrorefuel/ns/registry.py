"""现场命名空间注册表。

现场地址统一写成 ``<area>.<device>``，注册时带上设备类型。重复注册、解析
未注册地址都会抛出 :class:`NamespaceError`——控制台和审计共享同一套名字，
任何一边拼错地址都必须当场暴露，不能静默降级。
"""

from __future__ import annotations

from dataclasses import dataclass

from ..errors import NamespaceError


@dataclass(frozen=True)
class Device:
    """一个已登记的现场设备。"""

    area: str
    device: str
    kind: str

    @property
    def address(self) -> str:
        return f"{self.area}.{self.device}"

    def as_dict(self) -> dict:
        return {"area": self.area, "device": self.device, "kind": self.kind, "address": self.address}


class NamespaceRegistry:
    """区域／设备命名空间注册表。"""

    def __init__(self, unit: str = "station1") -> None:
        self._unit = unit
        self._devices: dict[str, Device] = {}

    @property
    def unit(self) -> str:
        return self._unit

    def register(self, area: str, device: str, kind: str) -> Device:
        """登记一个设备，地址重复即报错。"""

        if not area or not device or not kind:
            raise NamespaceError("区域、设备与类型都不能为空", component="ns")
        address = f"{area}.{device}"
        if address in self._devices:
            raise NamespaceError(f"地址已注册: {address}", component="ns")
        entry = Device(area, device, kind)
        self._devices[address] = entry
        return entry

    def resolve(self, address: str) -> Device:
        """按地址解析设备。"""

        try:
            return self._devices[address]
        except KeyError as error:
            raise NamespaceError(f"未注册地址: {address}", component="ns") from error

    def addresses(self) -> list[str]:
        """返回全部地址（排序后）。"""

        return sorted(self._devices)

    def describe(self) -> dict:
        """汇总命名空间，供状态快照读取。"""

        areas: dict[str, list[dict]] = {}
        for entry in self._devices.values():
            areas.setdefault(entry.area, []).append(entry.as_dict())
        return {
            "unit": self._unit,
            "count": len(self._devices),
            "addresses": self.addresses(),
            "areas": areas,
        }
