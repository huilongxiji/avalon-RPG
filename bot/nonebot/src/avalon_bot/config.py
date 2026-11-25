"""bot 前端配置：全部来自 NoneBot 自己的配置（本目录的 .env 和 .env.<ENVIRONMENT>），
与仓库根目录的 .env 无关。"""

from __future__ import annotations

from nonebot import get_plugin_config

from .tool.config import Config as MessageConfig


class BotConfig(MessageConfig):
    avalon_api_url: str = "http://127.0.0.1:7900"
    avalon_api_token: str = ""


def bot_config() -> BotConfig:
    return get_plugin_config(BotConfig)
