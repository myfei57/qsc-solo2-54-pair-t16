"""命令行入口。

五个子命令覆盖日常使用：

``serve``   启动控制台 HTTP 服务，可选地在启动后探测接口；
``demo``    在本地跑一遍完整流程（启动 → 卸氢 → 增压充瓶 → 加注 → 停止 →
            泄漏采样 → 并发探测 → 基线标定），用于交付前的真实运行检查；
``status``  打印当前状态快照；
``config``  打印生效配置；
``reset``   清掉落盘的平台计数。
"""

from __future__ import annotations

import argparse
import json
import sys
import time

from .app import Platform, build_platform
from .clock import ManualClock, SystemClock
from .config import config_to_mapping, default_config, load_config
from .console.server import ConsoleServer, probe_endpoints
from .errors import HydroError

DEFAULT_PROBE_PATHS = ("/api/status", "/api/readiness", "/api/topology", "/api/audit")


def _build(args: argparse.Namespace) -> Platform:
    config = load_config(args.config) if getattr(args, "config", None) else default_config()
    if getattr(args, "storage_root", None):
        return build_platform(config, storage_root=args.storage_root)
    return Platform(config=config)


def _dump(payload: object) -> None:
    print(json.dumps(payload, ensure_ascii=False, indent=2, default=str))


def _cmd_serve(args: argparse.Namespace) -> int:
    platform = _build(args)
    server = ConsoleServer(platform, host=args.host, port=args.port)
    base_url = server.start()
    payload: dict = {"listening": base_url, "routes": server.api.routes()}
    if args.probe:
        payload["probe"] = probe_endpoints(base_url, list(DEFAULT_PROBE_PATHS))
    _dump(payload)
    if args.duration > 0:
        try:
            time.sleep(args.duration)
        except KeyboardInterrupt:  # pragma: no cover - 交互路径
            pass
        server.stop()
        return 0
    try:
        while True:
            time.sleep(1.0)
    except KeyboardInterrupt:  # pragma: no cover - 交互路径
        server.stop()
    return 0


def _cmd_demo(args: argparse.Namespace) -> int:
    clock = ManualClock() if args.fast else SystemClock()
    config_path = getattr(args, "config", None)
    config = load_config(config_path) if config_path else default_config()
    platform = build_platform(config, clock=clock, storage_root=getattr(args, "storage_root", None))
    # 演示从干净基线起步：先清掉上一轮落盘的计数与运行态。
    platform.reset_state()

    startup = platform.start()
    unload = platform.unload(hose_pressure_mpa=20.0, target_kg=args.target_kg)
    pressurize = platform.pressurize(inlet_pressure_mpa=12.0, flow_kg_per_min=4.0, charge_kg=12.0)
    disturbance = platform.disturb_buffer(delta_mpa=-1.0)
    fill = platform.fill(vehicle="vehicle01", rate_kg_per_min=3.0, steps=args.steps)
    stop = platform.stop_fill()
    cycles = [platform.cycle(dt=1.0) for _ in range(6)]
    leak = platform.sample_leak(concentration_ppm=4200.0)
    clock.advance(config.leak.hold_s + 1.0)
    leak_reset = platform.release_leak()
    concurrency = platform.concurrency_probe(rounds=args.rounds)
    calibration = platform.calibrate_baseline(target_mpa=42.0)
    shutdown = platform.stop()

    # 演示自检用临时端口，避免和本机常驻服务抢 8080。
    server = ConsoleServer(platform, port=0)
    base_url = server.start()
    probe = probe_endpoints(base_url, list(DEFAULT_PROBE_PATHS))
    server.stop()

    report = {
        "startup": startup,
        "unload": {"ok": unload["ok"], "steps": [step["action"] for step in unload["steps"]]},
        "pressurize": {"ok": pressurize["ok"], "steps": [step["action"] for step in pressurize["steps"]]},
        "disturbance": disturbance,
        "fill": {"ok": fill["ok"], "steps": [step["action"] for step in fill["steps"]]},
        "stop": {"ok": stop["ok"], "steps": [step["action"] for step in stop["steps"]]},
        "cycles_run": len(cycles),
        "last_cycle": cycles[-1],
        "leak": leak,
        "leak_reset": leak_reset,
        "concurrency": concurrency,
        "calibration": calibration,
        "shutdown": shutdown,
        "probe": probe,
        "audit": platform.audit.summary(),
    }
    _dump(report)
    failures = [name for name, item in probe.items() if not item["ok"]]
    for operation in (unload, pressurize, fill, stop):
        if not operation["ok"]:
            failures.extend(operation["violations"])
    if not stop["ok"]:
        failures.append("stop_fill_not_completed")
    if failures:
        print(f"检查未通过: {failures}", file=sys.stderr)
        return 1
    return 0


def _cmd_status(args: argparse.Namespace) -> int:
    platform = _build(args)
    payload = platform.status()
    payload["topology"] = platform.topology_summary()
    payload["namespaces"] = platform.namespaces_describe()
    payload["trend"] = platform.trend.snapshot()
    _dump(payload)
    return 0


def _cmd_config(args: argparse.Namespace) -> int:
    config_path = getattr(args, "config", None)
    config = load_config(config_path) if config_path else default_config()
    _dump(config_to_mapping(config))
    return 0


def _cmd_reset(args: argparse.Namespace) -> int:
    platform = _build(args)
    _dump(platform.reset_state())
    return 0


def build_parser() -> argparse.ArgumentParser:
    """构造命令行解析器。"""

    common = argparse.ArgumentParser(add_help=False)
    common.add_argument("--config", help="JSON 配置文件路径", default=argparse.SUPPRESS)
    common.add_argument("--storage-root", help="覆盖状态存储目录", default=argparse.SUPPRESS)
    parser = argparse.ArgumentParser(
        prog="hydrorefuel", description="加氢站卸氢增压与加注顺序控制服务", parents=[common]
    )
    sub = parser.add_subparsers(dest="command", required=True)

    serve = sub.add_parser("serve", help="启动控制台服务", parents=[common])
    serve.add_argument("--host", default="127.0.0.1")
    serve.add_argument("--port", type=int, default=8080)
    serve.add_argument("--duration", type=float, default=0.0, help="运行多少秒后退出，0 表示常驻")
    serve.add_argument("--probe", action="store_true", help="启动后探测接口")
    serve.set_defaults(func=_cmd_serve)

    demo = sub.add_parser("demo", help="跑一遍完整流程", parents=[common])
    demo.add_argument("--vehicles", type=int, default=1, help="演示的车辆数量（保留兼容）")
    demo.add_argument("--target-kg", type=float, default=20.0, help="卸氢目标质量")
    demo.add_argument("--steps", type=int, default=3, help="加注阶梯数")
    demo.add_argument("--rounds", type=int, default=24, help="并发探测轮数")
    demo.add_argument("--fast", action="store_true", help="使用可推进时钟，跳过真实等待")
    demo.set_defaults(func=_cmd_demo)

    status = sub.add_parser("status", help="打印状态快照", parents=[common])
    status.set_defaults(func=_cmd_status)

    config = sub.add_parser("config", help="打印生效配置", parents=[common])
    config.set_defaults(func=_cmd_config)

    reset = sub.add_parser("reset", help="清掉落盘的平台计数", parents=[common])
    reset.set_defaults(func=_cmd_reset)
    return parser


def main(argv: list[str] | None = None) -> int:
    """命令行主入口。"""

    for stream in (sys.stdout, sys.stderr):
        reconfigure = getattr(stream, "reconfigure", None)
        if callable(reconfigure):
            reconfigure(encoding="utf-8", errors="backslashreplace")
    parser = build_parser()
    args = parser.parse_args(argv)
    try:
        return int(args.func(args))
    except HydroError as error:
        print(json.dumps(error.as_record(), ensure_ascii=False), file=sys.stderr)
        return 2
