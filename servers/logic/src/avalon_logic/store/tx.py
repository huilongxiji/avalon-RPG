"""事务：一次要改多张表的操作都包在事务里，中途抛出任何异常都会自动回滚。

用法::

    from avalon_logic.store.tx import transaction, atomic

    async with transaction("game"):
        ...                      # 抛出 GameError 等异常 → 整个事务回滚

    @atomic("game")
    async def settle(...):
        ...

SQLite 同一时间只允许一个写事务，所以同一个库的写操作会自动排队，不会互相覆盖。
"""

from __future__ import annotations

from tortoise.transactions import atomic as _atomic
from tortoise.transactions import in_transaction

from .orm import DATABASES


def _check(db: str) -> str:
    if db not in DATABASES:
        raise ValueError(f"没有这个数据库：{db}，可选：{'、'.join(DATABASES)}")
    return db


def transaction(db: str):
    """返回异步上下文管理器；退出时成功则提交，抛异常则回滚。"""
    return in_transaction(_check(db))


def atomic(db: str):
    """装饰器：整个函数在一个事务里执行。"""
    return _atomic(_check(db))
