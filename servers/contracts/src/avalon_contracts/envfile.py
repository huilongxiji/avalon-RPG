"""读取servers/.env 的小工具（不依赖第三方库）。

已经存在的环境变量优先，不会被 .env 覆盖。
"""

from __future__ import annotations

import os
from pathlib import Path


def find_root(start: Path | None = None) -> Path:
    """从 start 向上找含 avalon.toml 的目录，作为仓库根目录；找不到就用当前目录。"""
    here = (start or Path.cwd()).resolve()
    for folder in (here, *here.parents):
        if (folder / "avalon.toml").is_file():
            return folder
    return Path.cwd().resolve()


def load_env(path: Path | None = None) -> dict[str, str]:
    """把 .env 里的 KEY=VALUE 写入环境变量（已存在的不覆盖），返回读到的内容。"""
    env_path = path or (find_root() / "servers" / ".env")
    loaded: dict[str, str] = {}
    if not env_path.is_file():
        return loaded
    for raw in env_path.read_text(encoding="utf-8").splitlines():
        line = raw.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        key = key.strip()
        value = value.split(" #", 1)[0].strip().strip('"').strip("'")
        loaded[key] = value
        os.environ.setdefault(key, value)
    return loaded
