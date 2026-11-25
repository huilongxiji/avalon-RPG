"""启动 API 后端：avalon-api [--reload]

监听地址和端口来自servers/.env 的 AVALON_API_HOST / AVALON_API_PORT。
"""

from __future__ import annotations

import sys

import uvicorn

from .config import get_settings


def main() -> int:
    settings = get_settings()
    reload = "--reload" in sys.argv[1:]
    uvicorn.run(
        "avalon_api.server:app",
        host=settings.host,
        port=settings.port,
        reload=reload,
        reload_dirs=[str(settings.root / "servers" / "api" / "src"), str(settings.root / "servers" / "contracts" / "src")] if reload else None,
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
