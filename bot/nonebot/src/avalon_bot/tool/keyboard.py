"""Keyboard 行/整体构造。"""

from __future__ import annotations

from typing import Iterable, Sequence

from .button import Button
from .constants import KEYBOARD_MAX_COLS, KEYBOARD_MAX_ROWS


class Keyboard:
    """拼装 keyboard.content.rows（最多 5 行 × 每行 5 个）。"""

    __slots__ = ("_rows",)

    def __init__(self, rows: Sequence[Sequence[Button | dict]] | None = None) -> None:
        self._rows: list[list[Button | dict]] = []
        if rows:
            for row in rows:
                self.add_row(*row)

    def add_row(self, *buttons: Button | dict) -> "Keyboard":
        if len(self._rows) >= KEYBOARD_MAX_ROWS:
            raise ValueError(f"keyboard 最多 {KEYBOARD_MAX_ROWS} 行")
        if len(buttons) > KEYBOARD_MAX_COLS:
            raise ValueError(f"每行最多 {KEYBOARD_MAX_COLS} 个按钮")
        self._rows.append(list(buttons))
        return self

    def extend_rows(
        self, rows: Iterable[Sequence[Button | dict]]
    ) -> "Keyboard":
        for row in rows:
            self.add_row(*row)
        return self

    @staticmethod
    def _btn_dict(btn: Button | dict) -> dict:
        if isinstance(btn, Button):
            return btn.to_dict()
        return btn

    def to_dict(self) -> dict:
        return {
            "content": {
                "rows": [
                    {"buttons": [self._btn_dict(b) for b in row]}
                    for row in self._rows
                ]
            }
        }

    @classmethod
    def from_rows(cls, *rows: Sequence[Button | dict]) -> "Keyboard":
        """支持两种写法::

            Keyboard.from_rows([btn_a, btn_b], [btn_c])
            Keyboard.from_rows([[btn_a, btn_b], [btn_c]])
        """
        if (
            len(rows) == 1
            and rows[0]
            and isinstance(rows[0][0], (list, tuple))
        ):
            return cls(rows[0])  # type: ignore[arg-type]
        return cls(rows)

    @classmethod
    def single(cls, *buttons: Button | dict) -> "Keyboard":
        kb = cls()
        kb.add_row(*buttons)
        return kb

    @classmethod
    def normalize(cls, keyboard: "Keyboard | dict | list | None") -> dict | None:
        """将 Keyboard / dict / 行列表 规范为 keyboard dict。"""
        if keyboard is None:
            return None
        if isinstance(keyboard, Keyboard):
            return keyboard.to_dict()
        if isinstance(keyboard, dict):
            if "content" in keyboard:
                return keyboard
            return {"content": keyboard} if "rows" in keyboard else keyboard
        if isinstance(keyboard, list):
            return cls.from_rows(keyboard).to_dict()
        raise TypeError(f"不支持的 keyboard 类型: {type(keyboard)!r}")
