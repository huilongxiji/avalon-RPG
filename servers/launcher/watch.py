"""轮询组件源码的修改、增删，等待文件稳定后只发出一次重载通知。"""
from __future__ import annotations

import time
from pathlib import Path
from typing import Callable

IGNORED = {"__pycache__", ".git", ".venv", "node_modules", "data", ".pytest_cache", ".ruff_cache"}
SUFFIXES = {".py", ".json", ".toml", ".lock", ".yaml", ".yml", ".html", ".ts", ".vue", ".css"}


class SourceWatcher:
    def __init__(self, debounce: float = 0.6, clock: Callable[[], float] = time.monotonic):
        self.debounce = debounce
        self.clock = clock
        self.snapshots: dict[str, dict[str, tuple[int, int]]] = {}
        self.pending: dict[str, float] = {}

    @staticmethod
    def snapshot(paths: tuple[Path, ...]) -> dict[str, tuple[int, int]]:
        result = {}
        for root in paths:
            candidates = root.rglob("*") if root.is_dir() else (root,)
            for path in candidates:
                if any(part in IGNORED for part in path.parts) or path.name.startswith("test_"):
                    continue
                if path.suffix not in SUFFIXES or path.is_symlink():
                    continue
                try:
                    if not path.is_file():
                        continue
                    stat = path.stat()
                except OSError:
                    continue
                result[str(path)] = (stat.st_mtime_ns, stat.st_size)
        return result

    def changed(self, service) -> bool:
        key = service.key
        snapshot = self.snapshot(service.watch_paths)
        previous = self.snapshots.get(key)
        self.snapshots[key] = snapshot
        if previous is None:
            return False
        now = self.clock()
        if snapshot != previous:
            self.pending[key] = now
            return False
        pending = self.pending.get(key)
        if pending is not None and now - pending >= self.debounce:
            del self.pending[key]
            return True
        return False
