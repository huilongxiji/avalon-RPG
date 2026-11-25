"""系统状态（仅管理员）：检查 QQ → bot 前端 → API 后端 → 逻辑后端 这条链路是否通。"""

from __future__ import annotations

from avalon_contracts.errors import GameError
from nonebot import on_command
from nonebot.adapters.onebot.v11 import MessageEvent
from nonebot.matcher import Matcher
from nonebot.permission import SUPERUSER
from nonebot.plugin import PluginMetadata

from ... import api_client
from ...game_client import invalidate_report
from ...tool.official import event_openid

__plugin_meta__ = PluginMetadata(
    name="系统状态",
    description="管理员查看新系统各服务是否正常",
    usage="/系统状态",
    type="application",
    supported_adapters={"~onebot.v11"},
)

status_cmd = on_command("系统状态", permission=SUPERUSER, priority=10, block=True)


@status_cmd.handle()
async def handle_status(matcher: Matcher, event: MessageEvent) -> None:
    try:
        await invalidate_report(event_openid(event))
    except RuntimeError:
        pass
    lines = ["新系统状态", "- bot 前端：正常"]
    try:
        data = await api_client.get("/api/v1/system/health")
    except GameError as exc:
        lines.append(f"- API 后端：无法访问（{exc.message}）")
        await matcher.finish("\n".join(lines))
        return
    lines.append("- API 后端：正常")
    logic = (data or {}).get("logic")
    if not logic:
        lines.append("- 逻辑后端：无法访问")
    else:
        dbs = (logic.get("extra") or {}).get("databases", {})
        db_text = "、".join(f"{k}{'正常' if v else '异常'}" for k, v in dbs.items()) or "未知"
        rules = logic.get("rules_version")
        lines.append(f"- 逻辑后端：{'正常' if logic.get('ok') else '异常'}（数据库：{db_text}）")
        lines.append(f"- 当前规则版本：{rules if rules is not None else '尚未导入规则'}")
    await matcher.finish("\n".join(lines))
