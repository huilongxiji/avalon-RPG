"""API 后端配置：只从servers/.env 读监听地址、端口和令牌，其余都是固定值。"""

from __future__ import annotations

import os
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path

from avalon_contracts.envfile import find_root, load_env

LOGIC_URL = "http://127.0.0.1:7901"
CTL_URL = "http://127.0.0.1:7902"
PLACEHOLDER_PREFIX = "请改成"


@dataclass(frozen=True)
class Settings:
    root: Path
    data_dir: Path
    host: str
    port: int
    internal_token: str
    # 服务令牌：{名称: 令牌}；bot 用来调玩家接口，sim 用来调模拟接口
    service_tokens: dict[str, str]
    web_cookie_secure: bool = False


def _token(name: str) -> str:
    value = os.environ.get(name, "").strip()
    return "" if value.startswith(PLACEHOLDER_PREFIX) else value


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    root = find_root()
    load_env(root / "servers" / ".env")
    data_dir = root / "data"
    data_dir.mkdir(parents=True, exist_ok=True)
    tokens = {name: _token(f"AVALON_{name.upper()}_TOKEN") for name in ("bot", "sim")}
    return Settings(
        root=root,
        data_dir=data_dir,
        host=os.environ.get("AVALON_API_HOST", "").strip() or "127.0.0.1",
        port=int(os.environ.get("AVALON_API_PORT", "").strip() or 7900),
        internal_token=os.environ.get("AVALON_INTERNAL_TOKEN", "").strip(),
        service_tokens={k: v for k, v in tokens.items() if v},
        web_cookie_secure=os.environ.get("AVALON_WEB_COOKIE_SECURE", "").lower() in {"1", "true", "yes"},
    )
