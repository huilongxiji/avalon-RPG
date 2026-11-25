"""QQ 官方 Markdown / Keyboard 常量。"""

from __future__ import annotations

from enum import IntEnum


class ActionType(IntEnum):
    """按钮 action.type。"""

    URL = 0
    CALLBACK = 1
    COMMAND = 2
    NATIVE = 3
    SUBSCRIBE = 4


class Style(IntEnum):
    """按钮 render_data.style。"""

    GRAY = 0
    BLUE = 1
    RED_TEXT = 3
    BLUE_FILL = 4


class PermissionType(IntEnum):
    """按钮 action.permission.type。"""

    SPECIFY_USER = 0
    ADMIN = 1
    EVERYONE = 2
    SPECIFY_ROLE = 3


MODAL_CONTENT_MAX = 40
MODAL_BTN_TEXT_MAX = 4
KEYBOARD_MAX_ROWS = 5
KEYBOARD_MAX_COLS = 5

DEFAULT_UNSUPPORT_TIPS = "当前 QQ 版本不支持此按钮，请升级"
