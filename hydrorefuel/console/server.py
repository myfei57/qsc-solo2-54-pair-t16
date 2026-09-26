"""控制台 HTTP 服务。

使用标准库 ``ThreadingHTTPServer``，每个请求交给 :class:`Api` 处理并把返回
的字典编码成 JSON。访问路径会写进审计（只记路径不记正文），因此控制台动作
与自动循环动作在审计里能一眼区分。
"""

from __future__ import annotations

import json
import threading
import urllib.error
import urllib.request
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import parse_qs, urlsplit

from ..app import Platform
from ..eventbus import Event
from .api import Api


class _Handler(BaseHTTPRequestHandler):
    server_version = "hydrorefuel-console/1.0"

    def log_message(self, format: str, *args: object) -> None:  # noqa: A002 - 覆盖基类签名
        # 不往 stderr 刷访问日志；访问路径交给服务器记进审计。
        self.server.record_access(self.path)  # type: ignore[attr-defined]

    def do_GET(self) -> None:  # noqa: N802 - 基类约定
        self._dispatch("GET")

    def do_POST(self) -> None:  # noqa: N802 - 基类约定
        self._dispatch("POST")

    def _dispatch(self, method: str) -> None:
        parsed = urlsplit(self.path)
        length = int(self.headers.get("Content-Length") or 0)
        raw = self.rfile.read(length) if length else b""
        try:
            body = json.loads(raw.decode("utf-8")) if raw else {}
        except json.JSONDecodeError:
            body = {}
        if not isinstance(body, dict):
            body = {}
        query = {key: values[-1] for key, values in parse_qs(parsed.query).items()}
        status, payload = self.server.api.handle(method, parsed.path, query, body)  # type: ignore[attr-defined]
        data = json.dumps(payload, ensure_ascii=False, default=str).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(data)))
        self.end_headers()
        self.wfile.write(data)


class _ConsoleHTTPServer(ThreadingHTTPServer):
    daemon_threads = True
    allow_reuse_address = True

    def __init__(self, address: tuple[str, int], api: Api, platform: Platform) -> None:
        super().__init__(address, _Handler)
        self.api = api
        self.platform = platform

    def record_access(self, path: str) -> None:
        self.platform.bus.publish(
            Event.of("console", "console", "http_access", severity="notice", path=path)
        )


class ConsoleServer:
    """控制台服务封装，负责在后台线程里起停 ``ThreadingHTTPServer``。"""

    def __init__(self, platform: Platform, host: str = "127.0.0.1", port: int = 8080) -> None:
        self._platform = platform
        self._host = host
        self._port = port
        self._server: _ConsoleHTTPServer | None = None
        self._thread: threading.Thread | None = None
        self._api = Api(platform)

    @property
    def api(self) -> Api:
        return self._api

    @property
    def port(self) -> int:
        if self._server is None:
            return self._port
        return int(self._server.server_address[1])

    def start(self) -> str:
        """启动服务，返回基础 URL。"""

        if self._server is not None:
            return self.base_url()
        self._server = _ConsoleHTTPServer((self._host, self._port), self._api, self._platform)
        self._thread = threading.Thread(
            target=self._server.serve_forever, name="hydrorefuel-console", daemon=True
        )
        self._thread.start()
        return self.base_url()

    def base_url(self) -> str:
        """返回基础 URL（端口为实际监听端口）。"""

        host = self._host if self._host not in ("0.0.0.0", "") else "127.0.0.1"
        return f"http://{host}:{self.port}"

    def stop(self) -> None:
        """停止服务。"""

        if self._server is None:
            return
        self._server.shutdown()
        self._server.server_close()
        if self._thread is not None:
            self._thread.join(timeout=5)
        self._server = None
        self._thread = None


def probe_endpoints(base_url: str, paths: list[str]) -> dict:
    """对控制台各接口发真实 HTTP 请求，返回每个接口的健康结果。"""

    results: dict[str, dict] = {}
    for path in paths:
        url = f"{base_url}{path}"
        try:
            with urllib.request.urlopen(url, timeout=5) as response:
                payload = json.loads(response.read().decode("utf-8"))
                results[path] = {"ok": response.status == 200, "status": response.status, "keys": sorted(payload)[:6]}
        except (urllib.error.URLError, OSError, json.JSONDecodeError) as error:
            results[path] = {"ok": False, "error": str(error)}
    return results
