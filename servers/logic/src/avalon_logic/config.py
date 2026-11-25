"""逻辑后端配置。

只从servers/.env 读一项：AVALON_INTERNAL_TOKEN。其余都是固定值：
数据库在仓库根目录 data/ 下，只监听本机 127.0.0.1:7901。
"""

from __future__ import annotations

import os
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path

from avalon_contracts.envfile import find_root, load_env

HOST = "127.0.0.1"
PORT = 7901
SIM_WORKERS = 2          # 同时运行的模拟进程数（玩家请求优先）


@dataclass(frozen=True)
class Settings:
    root: Path
    data_dir: Path
    internal_token: str


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    root = find_root()
    load_env(root / "servers" / ".env")
    data_dir = root / "data"
    data_dir.mkdir(parents=True, exist_ok=True)
    return Settings(
        root=root,
        data_dir=data_dir,
        internal_token=os.environ.get("AVALON_INTERNAL_TOKEN", "").strip(),
    )
