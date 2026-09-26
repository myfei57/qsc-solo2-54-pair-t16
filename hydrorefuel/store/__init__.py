"""文件型持久化。

``JsonStore`` 保存"当前态"文档（每个文档一个 JSON 文件，写时先落临时文件
再原子替换）；``JsonlJournal`` 保存"流水"（按分段追加，只追加不重写）。两者
都落在平台配置的 ``storage_root`` 下。
"""

from __future__ import annotations

from .journal import JsonlJournal
from .jsonfile import JsonStore

__all__ = ["JsonStore", "JsonlJournal"]
