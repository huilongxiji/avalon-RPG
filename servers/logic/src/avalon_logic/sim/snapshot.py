"""在提交时冻结完整规则；同一个草稿再次修改也不会改变已提交的模拟。"""

from __future__ import annotations

import hashlib
import json

from avalon_contracts.errors import GameError
from pydantic import TypeAdapter

from ..engine.ruleset import RuleError
from ..rules.store import RuleData, active_version_id, load_data
from ..store.models.rules import RuleVersion
from ..store.tx import transaction

DATA = TypeAdapter(RuleData)


async def capture(selector: str) -> tuple[int, str, dict]:
    async with transaction("rules"):
        if selector == "active":
            version_id = await active_version_id()
        else:
            raw = selector.removeprefix("draft:")
            if not raw.isdigit() or int(raw) < 1:
                raise GameError("invalid", "规则版本应为 active、版本编号或 draft:编号")
            version_id = int(raw)
        version = await RuleVersion.get_or_none(id=version_id) if version_id else None
        if version is None:
            raise GameError("not_found", "指定的规则版本不存在")
        if selector.startswith("draft:") and version.status != "draft":
            raise GameError("invalid", "指定的版本不是草稿")
        data = await load_data(version.id)
    try:
        data.compile(version.id)
    except RuleError as exc:
        raise GameError("rules_invalid", str(exc)) from exc
    payload = DATA.dump_python(data, mode="json")
    encoded = json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    return version.id, hashlib.sha256(encoded.encode()).hexdigest(), payload
