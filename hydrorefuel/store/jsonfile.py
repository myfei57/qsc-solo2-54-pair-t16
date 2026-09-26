"""原子 JSON 文档存储。

每个文档一个 ``<doc_id>.json`` 文件。写入时先写同目录下的临时文件再
``os.replace`` 原子替换，保证中途掉电不会留下半截文档；读取时容忍文件
不存在（返回 ``None``），由调用方决定是否使用默认值。
"""

from __future__ import annotations

import json
import os
import tempfile
import threading
from typing import Any

from ..errors import StorageError


class JsonStore:
    """目录形式的 JSON 文档存储。"""

    def __init__(self, root: str) -> None:
        self._root = os.path.abspath(root)
        self._lock = threading.RLock()
        os.makedirs(self._root, exist_ok=True)

    @property
    def root(self) -> str:
        return self._root

    def path_of(self, doc_id: str) -> str:
        """返回某文档对应的文件路径。"""

        return os.path.join(self._root, f"{doc_id}.json")

    def exists(self, doc_id: str) -> bool:
        """文档文件是否存在。"""

        return os.path.isfile(self.path_of(doc_id))

    def write(self, doc_id: str, payload: Any) -> str:
        """原子写入一个文档，返回最终文件路径。"""

        target = self.path_of(doc_id)
        with self._lock:
            try:
                handle = tempfile.NamedTemporaryFile(
                    "w",
                    encoding="utf-8",
                    dir=self._root,
                    prefix=f".{doc_id}.",
                    suffix=".tmp",
                    delete=False,
                )
                with handle:
                    json.dump(payload, handle, ensure_ascii=False, indent=2)
                    handle.flush()
                    os.fsync(handle.fileno())
                os.replace(handle.name, target)
            except OSError as error:
                raise StorageError(f"写入文档 {doc_id} 失败: {error}", component="store") from error
        return target

    def read(self, doc_id: str) -> Any | None:
        """读取一个文档，不存在时返回 ``None``。"""

        target = self.path_of(doc_id)
        with self._lock:
            if not os.path.isfile(target):
                return None
            try:
                with open(target, "r", encoding="utf-8") as handle:
                    return json.load(handle)
            except (OSError, json.JSONDecodeError) as error:
                raise StorageError(f"读取文档 {doc_id} 失败: {error}", component="store") from error

    def remove(self, doc_id: str) -> bool:
        """删除一个文档，返回是否真的删掉了文件。"""

        target = self.path_of(doc_id)
        with self._lock:
            if not os.path.isfile(target):
                return False
            os.remove(target)
            return True

    def list_ids(self) -> list[str]:
        """列出全部文档标识（按文件名排序）。"""

        with self._lock:
            names = [name for name in os.listdir(self._root) if name.endswith(".json")]
        return sorted(name[: -len(".json")] for name in names)
