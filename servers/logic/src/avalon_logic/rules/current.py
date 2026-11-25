"""当前生效的规则快照。

逻辑后端启动时从规则库读出生效版本，编译成快照放在这里；网站改完规则、激活新版本后调用 reload()，
之后的计算都用新快照（正在算的战斗拿的是旧快照，会用旧规则算完，不会算到一半换规则）。
"""

from __future__ import annotations

import asyncio
import logging
from contextlib import contextmanager
from contextvars import ContextVar

from ..engine.ruleset import RuleSet

log = logging.getLogger("avalon_logic.rules")

_current: RuleSet | None = None
_staged: ContextVar[dict | None] = ContextVar("staged_rules", default=None)
_pinned: ContextVar[tuple | None] = ContextVar("pinned_rules", default=None)
_simulation: ContextVar[RuleSet | None] = ContextVar("simulation_rules", default=None)


@contextmanager
def using(rules: RuleSet):
    """模拟计算复用纯规则函数；局部指定版本，不发布、不改变线上生效版本。"""
    token = _simulation.set(rules)
    try:
        yield
    finally:
        _simulation.reset(token)


def get() -> RuleSet | None:
    """当前快照；规则库里还没有生效版本时是 None。"""
    if (simulation := _simulation.get()) is not None:
        return simulation
    stage = _staged.get()
    while stage is not None:
        if "rules" in stage:
            return stage["rules"]
        stage = stage["parent"]
    pinned = _pinned.get()
    if pinned is not None and pinned[0] is asyncio.current_task():
        return pinned[1]
    return _current


@contextmanager
def pinned():
    """一次业务事务使用同一个规则版本；下一次事务才读取热更新版本。"""
    token = _pinned.set((asyncio.current_task(), get()))
    try:
        yield
    finally:
        _pinned.reset(token)


def _publish(rules: RuleSet | None) -> None:
    global _current
    from ..engine.snapshot import RuleSnapshot, holder

    _current = rules
    holder.swap(RuleSnapshot(version_id=rules.version_id if rules else None))


@contextmanager
def staged():
    """定制宝石改规则时，提交前只有本次操作能看到新快照；失败丢弃暂存版本。"""
    parent = _staged.get()
    # 等待游戏锁期间仍读取最新已提交快照；未改规则的事务不能重新发布旧快照。
    stage = {"parent": parent}
    token = _staged.set(stage)
    try:
        yield
    except BaseException:
        raise
    else:
        if "rules" in stage:
            if parent is not None:
                parent["rules"] = stage["rules"]
            else:
                _publish(stage["rules"])
    finally:
        _staged.reset(token)


async def reload() -> RuleSet | None:
    """重新读取生效版本。编译出错时保留原来的快照并抛出异常。"""
    from .store import load_active

    rules = await load_active()
    stage = _staged.get()
    if stage is None:
        _publish(rules)
    else:
        stage["rules"] = rules
    if rules is None:
        log.warning("规则库尚未初始化：请导入并激活规则版本；世界 BOSS 结算将等待规则就绪。")
    else:
        log.info("已加载规则版本 %s：装备 %d、套装 %d、效果 %d、怪物 %d、副本 %d",
                 rules.version_id, len(rules.items), len(rules.sets), len(rules.effects),
                 len(rules.monsters), len(rules.dungeons))
    return rules
