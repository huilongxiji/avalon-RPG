"""直接探测当前部署的健康接口，不依赖旧编排器或猜测进程状态。"""

from __future__ import annotations

import asyncio
import os
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import httpx
from avalon_contracts.api.system import ServiceState

from .config import LOGIC_URL, get_settings

PROBE_TIMEOUT = 2.0


def _bot_values(path: Path) -> dict[str, str]:
    """只取定位健康接口所需的配置，不加载机器人令牌到 API 环境。"""
    if not path.is_file():
        return {}
    values = {}
    for raw in path.read_text(encoding="utf-8").splitlines():
        line = raw.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        key = key.strip()
        if key in {"ENVIRONMENT", "HOST", "PORT"}:
            values[key] = value.split(" #", 1)[0].strip().strip('"').strip("'")
    return values


def nonebot_url(root: Path) -> str:
    """与根 main.py 使用相同的配置选择和监听地址优先级。"""
    bot = root / "bot" / "nonebot"
    base = _bot_values(bot / ".env")
    environment = os.environ.get("ENVIRONMENT", base.get("ENVIRONMENT")) or "dev"
    values = {**base, **_bot_values(bot / f".env.{environment}.example"),
              **_bot_values(bot / f".env.{environment}")}
    host = os.environ.get("HOST", values.get("HOST")) or "127.0.0.1"
    port = int(os.environ.get("PORT", values.get("PORT")) or "7891")
    if not 1 <= port <= 65535:
        raise ValueError("NoneBot 端口不正确")
    if host in {"0.0.0.0", "::", "[::]"}:
        host = "127.0.0.1"
    if ":" in host and not host.startswith("["):
        host = f"[{host}]"
    return f"http://{host}:{port}"


def _state(key: str, name: str, status: str, message: str) -> ServiceState:
    return ServiceState(
        key=key, name=name, status=status, message=message,
        last_ok=datetime.now(timezone.utc) if status == "running" else None,
    )


async def _read(http: httpx.AsyncClient, url: str) -> tuple[int, Any]:
    # HTTPX 的分阶段超时之外，再限制一次探测的总耗时。
    async with asyncio.timeout(PROBE_TIMEOUT):
        response = await http.get(url)
        return response.status_code, response.json()


async def _health(http: httpx.AsyncClient, key: str, name: str, url: str) -> ServiceState:
    try:
        status, body = await _read(http, url + "/health")
    except (httpx.HTTPError, httpx.InvalidURL, TimeoutError, ValueError):
        return _state(key, name, "unhealthy", "健康接口不可达、超时或响应格式不正确")
    if status != 200 or not isinstance(body, dict) or body.get("service") != key:
        return _state(key, name, "unhealthy", "健康接口未返回预期服务的有效响应")
    if body.get("ok") is not True:
        return _state(key, name, "unhealthy", "服务已响应，但健康检查未通过")
    return _state(key, name, "running", "健康检查通过")


async def _onebot(http: httpx.AsyncClient, url: str) -> ServiceState:
    key, name = "goqbot", "goqbot（OneBot 连接）"
    try:
        status, body = await _read(http, url + "/health/onebot")
    except (httpx.HTTPError, httpx.InvalidURL, TimeoutError, ValueError):
        return _state(key, name, "unhealthy", "无法读取 OneBot 连接状态；未确认 QQ 在线")
    connected = body.get("connected") if isinstance(body, dict) else None
    if type(connected) is not int or connected < 0 or status not in {200, 503}:
        return _state(key, name, "unhealthy", "OneBot 连接探针返回异常；未确认 QQ 在线")
    if connected == 0:
        return _state(key, name, "offline", "尚无 OneBot 连接，请检查 goqbot 的登录和连接")
    if status != 200:
        return _state(key, name, "unhealthy", "OneBot 连接探针未通过；未确认 QQ 在线")
    return _state(key, name, "running", f"已建立 {connected} 个 OneBot 连接；未单独核验 QQ 登录状态")


async def probe_services(http: httpx.AsyncClient, bot_url: str | None) -> list[ServiceState]:
    """各探测相互独立；一个服务失败不会使其他服务的状态丢失。"""
    api = _state("api", "API 后端", "running", "当前 API 正在响应")
    if bot_url is None:
        logic = await _health(http, "logic", "逻辑后端", LOGIC_URL)
        bot = _state("bot", "NoneBot", "unhealthy", "无法读取 NoneBot 监听配置")
        goqbot = _state("goqbot", "goqbot（OneBot 连接）", "unhealthy", "NoneBot 地址不可用，无法确认连接状态")
    else:
        logic, bot, goqbot = await asyncio.gather(
            _health(http, "logic", "逻辑后端", LOGIC_URL),
            _health(http, "bot", "NoneBot", bot_url),
            _onebot(http, bot_url),
        )
        if bot.status != "running" and goqbot.status == "running":
            goqbot = _state("goqbot", "goqbot（OneBot 连接）", "unhealthy",
                           "NoneBot 健康检查未通过，无法确认连接探针的状态")
    return [api, logic, bot, goqbot]


async def service_states() -> list[ServiceState]:
    try:
        bot_url = nonebot_url(get_settings().root)
    except (OSError, ValueError):
        bot_url = None
    # 本机服务不经过系统代理；不携带网站、QQ 或内部服务令牌。
    async with httpx.AsyncClient(timeout=PROBE_TIMEOUT, trust_env=False, follow_redirects=False) as http:
        return await probe_services(http, bot_url)
