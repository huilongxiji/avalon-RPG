"""Tortoise ORM 配置：逻辑后端管理 rules / game / stats 三个库。

数据库文件固定在仓库根目录的 data/ 下。
表结构升级文件放在 avalon_logic/migrations/<库名>/，由 Tortoise 自带的迁移工具生成。
"""

from __future__ import annotations

from typing import Any

from ..config import get_settings

DATABASES = ("rules", "game", "stats")


def _sqlite_url(name: str, memory: bool) -> str:
    if memory:
        return "sqlite://:memory:"
    path = get_settings().data_dir / f"{name}.db"
    return f"sqlite://{path.as_posix()}"


def build_config(memory: bool = False) -> dict[str, Any]:
    """memory=True 时三个库都用内存库（测试和模拟任务的临时存档用）。"""
    return {
        "connections": {name: _sqlite_url(name, memory) for name in DATABASES},
        "apps": {
            name: {
                "models": [f"avalon_logic.store.models.{name}"],
                "default_connection": name,
                "migrations": f"avalon_logic.migrations.{name}",
            }
            for name in DATABASES
        },
        "use_tz": True,
        "timezone": "Asia/Seoul",
    }


# 给 Tortoise 迁移命令用：tortoise -c avalon_logic.store.orm.TORTOISE_ORM migrate
TORTOISE_ORM = build_config()


async def enable_wal() -> None:
    """三个库都开启 WAL 模式：读写互不阻塞。"""
    from tortoise import connections

    for name in DATABASES:
        conn = connections.get(name)
        await conn.execute_script("PRAGMA journal_mode=WAL; PRAGMA foreign_keys=ON;")
