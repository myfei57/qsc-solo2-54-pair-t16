"""分段 JSONL 流水日志。

流水只追加不重写，按 ``segment_limit`` 条一段滚动成 ``<topic>-00000.jsonl``、
``<topic>-00001.jsonl`` …。充装记录回放需要按段读取，因此同时提供段号列表、
单段读取和全量读取三种入口。
"""

from __future__ import annotations

import json
import os
import threading
from typing import Any

from ..errors import StorageError

MAX_SEGMENTS = 4096


class JsonlJournal:
    """按段落写入的 JSONL 流水。"""

    def __init__(self, root: str, topic: str, segment_limit: int = 512) -> None:
        self._root = os.path.abspath(root)
        self._topic = topic
        self._segment_limit = max(1, segment_limit)
        self._count = 0
        self._segment = 0
        self._lock = threading.RLock()
        os.makedirs(self._root, exist_ok=True)
        self._count = self._existing_count()

    @property
    def topic(self) -> str:
        return self._topic

    def _segment_path(self, index: int) -> str:
        return os.path.join(self._root, f"{self._topic}-{index:05d}.jsonl")

    def _existing_count(self) -> int:
        total = 0
        for index in range(MAX_SEGMENTS):
            path = self._segment_path(index)
            if not os.path.isfile(path):
                break
            with open(path, "r", encoding="utf-8") as handle:
                total += sum(1 for line in handle if line.strip())
        return total

    def append(self, record: Any) -> str:
        """追加一条记录，返回写入的段路径。"""

        with self._lock:
            index = self._count // self._segment_limit
            path = self._segment_path(index)
            try:
                with open(path, "a", encoding="utf-8") as handle:
                    handle.write(json.dumps(record, ensure_ascii=False) + "\n")
                    handle.flush()
                    os.fsync(handle.fileno())
            except OSError as error:
                raise StorageError(f"追加流水失败: {error}", component="store") from error
            self._count += 1
            self._segment = index
            return path

    def segments(self) -> list[str]:
        """返回已存在的段文件路径（按段号升序）。"""

        found: list[str] = []
        for index in range(MAX_SEGMENTS):
            path = self._segment_path(index)
            if not os.path.isfile(path):
                break
            found.append(path)
        return found

    def read_segment(self, index: int) -> list[dict]:
        """读取指定段。"""

        path = self._segment_path(index)
        if not os.path.isfile(path):
            return []
        return self._read_file(path)

    def read_all(self) -> list[dict]:
        """按段号顺序读取全部记录。"""

        records: list[dict] = []
        for path in self.segments():
            records.extend(self._read_file(path))
        return records

    def count(self) -> int:
        """返回累计写入条数。"""

        with self._lock:
            return self._count

    def active_segment(self) -> int:
        """返回当前正在写入的段号。"""

        with self._lock:
            return self._segment

    def _read_file(self, path: str) -> list[dict]:
        try:
            with open(path, "r", encoding="utf-8") as handle:
                return [json.loads(line) for line in handle if line.strip()]
        except (OSError, json.JSONDecodeError) as error:
            raise StorageError(f"读取流水 {path} 失败: {error}", component="store") from error
