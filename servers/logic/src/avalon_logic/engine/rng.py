"""可设种子的随机数：同样的规则版本 + 同样的种子 = 同样的战斗结果。

判定方式与旧版 bot 一致（旧版用 random.randrange(100) < 概率），所以同一个种子下
新旧引擎掷出的每一次点数都相同，可以逐场对拍。
"""

from __future__ import annotations

import random
import secrets
from collections.abc import Sequence
from typing import TypeVar

T = TypeVar("T")


class Rng:
    def __init__(self, seed: int | None = None) -> None:
        self.seed = seed if seed is not None else secrets.randbits(48)
        self._random = random.Random(self.seed)

    def roll(self, percent: float) -> bool:
        """按百分比判定：roll(30) 有 30% 概率为真。0 及以下必假，100 及以上必真（这两种不消耗随机数）。

        整数概率掷 0–99 的整数（与旧版一致）；带小数的概率按小数精度判定。
        """
        if percent <= 0:
            return False
        if percent >= 100:
            return True
        if float(percent).is_integer():
            return self._random.randrange(100) < percent
        return self._random.random() * 100 < percent

    def randrange(self, stop: int) -> int:
        return self._random.randrange(stop)

    def uniform(self, low: float, high: float) -> float:
        return self._random.uniform(low, high)

    def choice(self, items: Sequence[T]) -> T:
        return self._random.choice(items)

    def weighted(self, items: Sequence[T], weights: Sequence[float]) -> T:
        return self._random.choices(items, weights=weights, k=1)[0]

    def fork(self) -> "Rng":
        """派生一个独立的随机数（批量模拟时每场一个，结果仍可复现）。"""
        return Rng(self._random.getrandbits(48))
