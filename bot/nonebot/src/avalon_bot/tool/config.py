from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field


class Config(BaseModel):
    game_send_mode: Literal["markdown", "text"] = "markdown"
    game_layout_font: str = Field(default="")
