"""在读草稿之前串行化规则写操作，避免同类规则整表保存时丢失并发修改。"""

import asyncio
from functools import wraps
from weakref import WeakKeyDictionary

_locks = WeakKeyDictionary()


def serialized(function):
    @wraps(function)
    async def wrapped(*args, **kwargs):
        loop = asyncio.get_running_loop()
        lock = _locks.setdefault(loop, asyncio.Lock())
        async with lock:
            return await function(*args, **kwargs)
    return wrapped
