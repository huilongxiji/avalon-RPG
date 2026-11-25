"""检查并应用数据库表结构升级（命令：avalon-api-migrate）。

调用 Tortoise 自带的迁移工具：
- 某个库还没有任何迁移文件时（第一次运行），先生成初始迁移；
- 然后应用所有未执行的迁移。
第一次运行生成的迁移文件在 src/avalon_api/migrations/<库名>/ 下，请提交进 git。
"""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path

DATABASES = ("api",)

CONFIG = "avalon_api.store.orm.TORTOISE_ORM"
MIGRATIONS_DIR = Path(__file__).resolve().parent.parent / "migrations"


def _tortoise(*args: str) -> int:
    cmd = [sys.executable, "-m", "tortoise", "-c", CONFIG, *args]
    print("执行：" + " ".join(cmd[2:]))
    return subprocess.call(cmd)


def _has_migrations(app: str) -> bool:
    folder = MIGRATIONS_DIR / app
    return any(p.suffix == ".py" and p.name != "__init__.py" for p in folder.glob("*.py"))


def main() -> int:
    for app in DATABASES:
        if not _has_migrations(app):
            print(f"[{app}] 还没有迁移文件，生成初始迁移...")
            if _tortoise("makemigrations", app, "--name", "initial") != 0:
                print(f"[{app}] 生成初始迁移失败，请检查上面的错误信息。", file=sys.stderr)
                return 1
    print("应用表结构升级...")
    if _tortoise("migrate") != 0:
        print("应用表结构升级失败，请检查上面的错误信息。", file=sys.stderr)
        return 1
    print("数据库表结构已是最新。")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
