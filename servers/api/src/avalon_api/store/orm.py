"""Tortoise ORM 配置：api.db。"""

from __future__ import annotations

from typing import Any

from ..config import get_settings


def build_config(memory: bool = False) -> dict[str, Any]:
    url = "sqlite://:memory:" if memory else f"sqlite://{(get_settings().data_dir / 'api.db').as_posix()}"
    return {
        "connections": {"api": url},
        "apps": {
            "api": {
                "models": ["avalon_api.store.models"],
                "default_connection": "api",
                "migrations": "avalon_api.migrations.api",
            }
        },
        "use_tz": True,
        "timezone": "Asia/Seoul",
    }


TORTOISE_ORM = build_config()


async def enable_wal() -> None:
    from tortoise import connections

    await connections.get("api").execute_script("PRAGMA journal_mode=WAL; PRAGMA foreign_keys=ON;")
