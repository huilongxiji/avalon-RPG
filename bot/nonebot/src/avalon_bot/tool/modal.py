"""按钮二次确认弹窗 action.modal。"""

from __future__ import annotations

from .constants import MODAL_BTN_TEXT_MAX, MODAL_CONTENT_MAX


class Modal:
    """构造 action.modal。

    content ≤40 字且不能含 URL；confirm/cancel 文案各 ≤4 字。
    点「取消」不上报；点「确认」后才执行按钮动作。
    """

    __slots__ = ("content", "confirm_text", "cancel_text")

    def __init__(
        self,
        content: str,
        *,
        confirm_text: str = "确认",
        cancel_text: str = "取消",
        validate: bool = True,
    ) -> None:
        self.content = content or ""
        self.confirm_text = confirm_text or "确认"
        self.cancel_text = cancel_text or "取消"
        if validate:
            self._validate()

    def _validate(self) -> None:
        if "://" in self.content or "http" in self.content.lower():
            raise ValueError("modal.content 不能含 URL")
        if len(self.content) > MODAL_CONTENT_MAX:
            raise ValueError(
                f"modal.content 最多 {MODAL_CONTENT_MAX} 字，当前 {len(self.content)}"
            )
        if len(self.confirm_text) > MODAL_BTN_TEXT_MAX:
            raise ValueError(
                f"confirm_text 最多 {MODAL_BTN_TEXT_MAX} 字，当前 {len(self.confirm_text)}"
            )
        if len(self.cancel_text) > MODAL_BTN_TEXT_MAX:
            raise ValueError(
                f"cancel_text 最多 {MODAL_BTN_TEXT_MAX} 字，当前 {len(self.cancel_text)}"
            )

    def to_dict(self) -> dict:
        return {
            "content": self.content,
            "confirm_text": self.confirm_text,
            "cancel_text": self.cancel_text,
        }
