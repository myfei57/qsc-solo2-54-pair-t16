"""交付卫生硬门禁。

这一组用例把"不能出现脚手架与死代码"从口头要求变成可执行检查：

1. **符号引用**：生产模块里的每个模块级函数、类和类方法，都必须在本包里被
   真正引用过；只在测试里用到的符号同样算没人调用。
2. **模块可达**：从 ``hydrorefuel.__main__`` 出发沿 import 图求传递闭包，任何
   生产模块不在闭包内，说明有没人引用的文件混进了交付树。
3. **空壳函数**：函数体只有 ``pass``、``...`` 或空 ``return`` 的，属于占位实现。
4. **构建残留**：交付树不允许出现原平台遗留的构建残留文件与专用构建助手脚本。
"""

from __future__ import annotations

import ast
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
PACKAGE = ROOT / "hydrorefuel"

# 由运行时按约定调用的名字，不算死符号。
RUNTIME_HOOKS = {
    "__init__",
    "__post_init__",
    "__enter__",
    "__exit__",
    "__repr__",
    "__eq__",
    "__hash__",
    "do_GET",
    "do_POST",
    "do_PUT",
    "do_DELETE",
    "log_message",
    "main",
}

# 构建残留标记由片段拼出，避免把该类字样写进仓库本身。
FORBIDDEN_TOKEN = "".join(("ben", "zhi"))


def _module_name(path: Path) -> str:
    relative = path.relative_to(ROOT).with_suffix("")
    parts = list(relative.parts)
    if parts[-1] == "__init__":
        parts = parts[:-1]
    return ".".join(parts)


def _parse_sources() -> dict[str, ast.AST]:
    tree: dict[str, ast.AST] = {}
    for path in sorted(PACKAGE.rglob("*.py")):
        if "__pycache__" in path.parts:
            continue
        tree[_module_name(path)] = ast.parse(path.read_text(encoding="utf-8"), str(path))
    return tree


def _definitions(tree: ast.AST, module: str) -> list[dict]:
    found: list[dict] = []
    for node in tree.body:
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            found.append({"name": node.name, "module": module, "line": node.lineno})
        elif isinstance(node, ast.ClassDef):
            found.append({"name": node.name, "module": module, "line": node.lineno})
            for item in node.body:
                if isinstance(item, (ast.FunctionDef, ast.AsyncFunctionDef)):
                    found.append({"name": item.name, "module": module, "line": item.lineno})
    return found


def _usages(tree: ast.AST) -> list[str]:
    used: list[str] = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Name):
            used.append(node.id)
        elif isinstance(node, ast.Attribute):
            used.append(node.attr)
        elif isinstance(node, ast.Constant) and isinstance(node.value, str):
            for part in node.value.replace("/", ".").replace("-", ".").split("."):
                if part.isidentifier():
                    used.append(part)
    return used


def _resolve_import(module: str, node: ast.ImportFrom, is_package: bool) -> list[str]:
    base = node.module or ""
    if node.level:
        parts = module.split(".")
        parent = parts if is_package else parts[:-1]
        keep = max(0, len(parent) - (node.level - 1))
        base = ".".join(parent[:keep] + ([base] if base else []))
    resolved = [base] if base else []
    for alias in node.names:
        if alias.name != "*":
            resolved.append(f"{base}.{alias.name}" if base else alias.name)
    return [item for item in resolved if item]


def _is_package(module: str) -> bool:
    path = ROOT / (module.replace(".", "/") + ".py")
    if path.name == "__init__.py":
        return True
    return (ROOT / module.replace(".", "/") / "__init__.py").is_file()


def _import_graph(modules: dict[str, ast.AST]) -> dict[str, set[str]]:
    packages = {name for name in modules if _is_package(name)}
    graph: dict[str, set[str]] = {name: set() for name in modules}
    for name, tree in modules.items():
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                graph[name].update(alias.name for alias in node.names)
            elif isinstance(node, ast.ImportFrom):
                graph[name].update(_resolve_import(name, node, name in packages))
    return graph


def test_no_unreferenced_symbols_in_package():
    modules = _parse_sources()
    usages: dict[str, int] = {}
    definitions: list[dict] = []
    for module, tree in modules.items():
        definitions.extend(_definitions(tree, module))
        for name in _usages(tree):
            usages[name] = usages.get(name, 0) + 1
    orphans = [
        item
        for item in definitions
        if usages.get(item["name"], 0) == 0
        and item["name"] not in RUNTIME_HOOKS
        and not item["module"].endswith("__main__")
    ]
    assert orphans == [], f"存在生成了但没人调用的符号: {orphans}"


def test_every_module_is_reachable_from_the_entrypoint():
    modules = _parse_sources()
    graph = _import_graph(modules)
    pending = [name for name in modules if name.endswith("__main__")]
    assert pending, "缺少 __main__ 入口"
    reachable: set[str] = set()
    while pending:
        current = pending.pop()
        if current in reachable:
            continue
        reachable.add(current)
        for target in graph.get(current, set()):
            candidates = [target]
            parts = target.split(".")
            for cut in range(len(parts) - 1, 0, -1):
                candidates.append(".".join(parts[:cut]))
            for candidate in candidates:
                if candidate in modules and candidate not in reachable:
                    pending.append(candidate)
    unreachable = sorted(
        name for name in modules if name not in reachable and not name.endswith("__main__")
    )
    assert unreachable == [], f"存在没人引用的模块: {unreachable}"


def test_no_placeholder_function_bodies():
    places: list[str] = []
    for module, tree in _parse_sources().items():
        for node in ast.walk(tree):
            if not isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                continue
            body = [
                item
                for item in node.body
                if not (isinstance(item, ast.Expr) and isinstance(item.value, ast.Constant))
            ]
            if len(body) != 1:
                continue
            only = body[0]
            if isinstance(only, ast.Pass):
                places.append(f"{module}:{node.lineno} {node.name} 只有 pass")
            elif isinstance(only, ast.Return) and only.value is None:
                places.append(f"{module}:{node.lineno} {node.name} 只有空 return")
            elif (
                isinstance(only, ast.Expr)
                and isinstance(only.value, ast.Constant)
                and only.value.value is Ellipsis
            ):
                places.append(f"{module}:{node.lineno} {node.name} 只有省略号")
    assert places == [], f"存在占位实现: {places}"


def test_delivery_tree_carries_no_build_leftovers():
    offenders: list[str] = []
    for path in sorted(ROOT.rglob("*")):
        parts = set(path.relative_to(ROOT).parts)
        if parts & {".git", "__pycache__", ".pytest_cache", "var", ".venv"}:
            continue
        if path.is_dir():
            continue
        lowered = path.name.lower()
        if FORBIDDEN_TOKEN in lowered:
            offenders.append(f"文件名: {path.relative_to(ROOT)}")
            continue
        if path.suffix in {".pyc", ".png", ".jpg", ".xlsx", ".zip"}:
            continue
        try:
            text = path.read_text(encoding="utf-8").lower()
        except (UnicodeDecodeError, OSError):
            continue
        if FORBIDDEN_TOKEN in text:
            offenders.append(f"文件内容: {path.relative_to(ROOT)}")
        if path.parent == ROOT and lowered.startswith(("build_", "build-")):
            offenders.append(f"专用构建助手: {path.relative_to(ROOT)}")
    assert offenders == [], f"交付树混入构建残留: {offenders}"


def test_shell_scripts_are_not_shipped():
    scripts = [
        path.relative_to(ROOT).as_posix()
        for path in ROOT.rglob("*.sh")
        if ".git" not in path.parts and "vendor" not in path.parts
    ]
    assert scripts == [], f"交付树不应带 shell 构建脚本: {scripts}"


def test_deadcode_tool_reports_clean():
    result = subprocess.run(
        [sys.executable, str(ROOT / "tools" / "deadcode.py"), str(PACKAGE)],
        capture_output=True,
        text=True,
        encoding="utf-8",
        check=False,
    )
    assert result.returncode == 0, result.stdout + result.stderr
    assert '"unused_symbols": []' in result.stdout
    assert '"unreachable_modules": []' in result.stdout
