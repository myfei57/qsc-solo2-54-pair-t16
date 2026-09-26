"""标识生成。

每次加注、每段卸氢、每条审计流水都需要一个全局唯一的标识。这里用标准库
``uuid`` 生成随机标识，并允许调用方带上业务前缀，让落盘文件名和事件里的
``op_id`` 一眼能看出属于哪类动作。
"""

from __future__ import annotations

import uuid


class IdFactory:
    """带前缀的唯一标识工厂。"""

    def __init__(self, prefix: str) -> None:
        if not prefix:
            raise ValueError("前缀不能为空")
        self._prefix = prefix
        self._issued = 0

    @property
    def prefix(self) -> str:
        return self._prefix

    def issued(self) -> int:
        """返回本工厂累计发出的标识数量。"""

        return self._issued

    def next(self) -> str:
        """生成一个新的 ``<prefix>-<随机段>`` 标识。"""

        self._issued += 1
        return f"{self._prefix}-{uuid.uuid4().hex[:12]}"
