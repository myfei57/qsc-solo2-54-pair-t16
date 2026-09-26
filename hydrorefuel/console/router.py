"""极简路径路由。

支持 ``/api/audit`` 这类静态路径与 ``/api/namespace/{address}`` 这类带参
路径。匹配按段比较：静态段必须相同，``{name}`` 段捕获任意非空段并放进参数
字典。
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Callable

Handler = Callable[[dict, dict], dict]


@dataclass(frozen=True)
class Route:
    """一条路由。"""

    method: str
    pattern: str
    handler: Handler

    def as_dict(self) -> dict:
        return {"method": self.method, "path": self.pattern}


class Router:
    """按方法与路径段匹配的路由表。"""

    def __init__(self) -> None:
        self._routes: list[Route] = []

    def add(self, method: str, pattern: str, handler: Handler) -> Route:
        """登记一条路由。"""

        route = Route(method.upper(), pattern, handler)
        self._routes.append(route)
        return route

    def routes(self) -> list[Route]:
        """返回全部路由。"""

        return list(self._routes)

    def match(self, method: str, path: str) -> tuple[Handler, dict] | None:
        """匹配一条路由，返回处理器与参数字典。"""

        wanted = [segment for segment in path.split("/") if segment]
        for route in self._routes:
            if route.method != method.upper():
                continue
            pattern = [segment for segment in route.pattern.split("/") if segment]
            if len(pattern) != len(wanted):
                continue
            params: dict[str, str] = {}
            for expected, actual in zip(pattern, wanted):
                if expected.startswith("{") and expected.endswith("}"):
                    params[expected[1:-1]] = actual
                elif expected != actual:
                    break
            else:
                return route.handler, params
        return None
