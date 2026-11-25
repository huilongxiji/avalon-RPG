"""启动逻辑后端：avalon-logic [--reload]"""

from __future__ import annotations

import sys

import uvicorn

from .config import HOST, PORT, get_settings


def main() -> int:
    root = get_settings().root
    reload = "--reload" in sys.argv[1:]
    uvicorn.run(
        "avalon_logic.server:app",
        host=HOST,
        port=PORT,
        reload=reload,
        reload_dirs=[str(root / "servers" / "logic" / "src"), str(root / "servers" / "contracts" / "src")] if reload else None,
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
