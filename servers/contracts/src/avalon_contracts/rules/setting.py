"""零散设定：回合上限、默认暴击伤害、全局机制、体力上限、背包上限、手续费比例……"""

from __future__ import annotations

from typing import Any

from pydantic import BaseModel

# 战斗内核用到的设定（默认值见 avalon_logic.rules.builtin）
BATTLE_SETTINGS: dict[str, str] = {
    "max_rounds": "回合上限",
    "draw_idle_rounds": "不限回合时，连续多少回合双方都没造成伤害算平局",
    "default_crit_dmg": "暴击伤害为 0 时使用的默认暴击伤害（%）",
    "monster_default_dodge": "怪物没填闪避率时的默认值（%）",
    "percent_stats": "百分比属性 → 它加成的属性，例如 atk_pct → atk",
    "global_effects": "全局机制：对所有战斗都生效的效果代号（例如碎晶本身的减防减抗）",
    "world_boss": "世界BOSS的生命、攻击",
}


class SettingDef(BaseModel):
    key: str
    value: Any
    description: str = ""
