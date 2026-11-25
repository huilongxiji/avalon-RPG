"""逻辑后端拥有定时结算任务；机器人离线也正常结算。"""

from __future__ import annotations

import asyncio
import logging
from contextlib import asynccontextmanager

from .ledger import delivery_loop
from .world_boss import world_boss_settle_if_due

log = logging.getLogger("avalon_logic.game.tasks")


async def settle_loop(interval: float = 30) -> None:
    while True:
        try:
            await world_boss_settle_if_due()
        except Exception:
            log.exception("世界 BOSS 结算失败，将在下一轮重试")
        await asyncio.sleep(interval)


@asynccontextmanager
async def background_tasks():
    tasks = [asyncio.create_task(settle_loop(), name="world-boss-settlement"),
             asyncio.create_task(delivery_loop(), name='stats-delivery')]
    try:
        yield
    finally:
        for task in tasks:
            task.cancel()
        await asyncio.gather(*tasks, return_exceptions=True)
