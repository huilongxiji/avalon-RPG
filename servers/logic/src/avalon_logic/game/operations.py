"""玩家 HTTP 操作的业务编排。这里组合事务和结果，机器人不参与任何数值计算。"""

from __future__ import annotations

import hashlib
import json
from contextlib import nullcontext
from dataclasses import asdict, is_dataclass
from datetime import date
from typing import Any

from avalon_contracts.api.game import AdminAction, Operation, RequestBody
from avalon_contracts.errors import GameError
from fastapi.encoders import jsonable_encoder

from ..rules.views import item_detail
from ..store.models.game import Account, CommandReceipt, GameAudit, MarketListing
from . import (
    bag,
    checkin,
    core,
    dungeon,
    economy,
    enhance,
    info,
    ledger,
    market,
    panel,
    props,
    sponsor,
    tower,
    tuning,
    world_boss,
)
from .constants import (
    EQUIP_SLOT_LABELS,
)


def checked(result: Any) -> Any:
    if hasattr(result, "ok") and not result.ok:
        detail = asdict(result) if is_dataclass(result) else {}
        detail.pop("ok", None)
        code = detail.pop("error", None) or "invalid"
        raise GameError(code, **detail)
    return result


def positive(value: Any, default: int | None = None) -> int:
    try:
        number = int(value) if value is not None else default
    except (TypeError, ValueError):
        number = None
    if number is None or number <= 0:
        raise GameError("invalid")
    return number


def slot_of(value: str) -> str:
    if value not in EQUIP_SLOT_LABELS:
        raise GameError("bad_slot")
    return value


def easter_codes() -> set[str]:
    # 保留旧版默认彩蛋码；规则配置可覆盖（空列表表示关闭）。
    raw = tuning.value('easter_codes')
    return {str(code).strip() for code in ([raw] if isinstance(raw, str) else raw) if str(code).strip()}


async def owned_item(name: str, level: int, temper: int) -> dict:
    item = core.item_by_name(name)
    if item is None:
        raise GameError("no_item")
    gem = await sponsor.sponsor_gem(name) if item.slot == 'gem' else None
    return {"item": item, "enhance": level, "temper": temper,
            "stats": info.item_stats_at(item, level, temper), "stat_meta": stat_meta(),
            "base_stats": info.item_stats_at(item, 0, temper),
            "next_stats": info.item_stats_at(item, level + 1, temper),
            "next_cost": info.enhance_step_cost(level), "total_cost": info.enhance_total_cost(level),
            "refund": info.enhance_refund(level), "temper_cap": tuning.value('temper_cap_pct'),
            "sponsor_features": sponsor.feature_descriptions(gem) if gem else [],
            "detail": item_detail(core.rules(), item.id)}


def stat_meta() -> list[dict]:
    return [{'key': k, 'name': s.name, 'percent': s.percent} for k, s in core.rules().stats.items() if s.show]


def boss_rules() -> dict:
    return {'settle_hour': tuning.value('world_boss_settle_hour'),
            'reward_tiers': tuning.value('world_boss_reward_tiers'),
            'participation_coins': tuning.value('world_boss_participation_coins')}


async def player_panel(openid: str) -> dict:
    base = await economy.get_panel(openid)
    if base is None:
        raise GameError("no_user")
    spec = await panel.battle_spec(openid)
    counts = panel.set_counts(await panel.worn_items(openid))
    sets = [{'name': name, 'count': count,
             'total': max((t.pieces for t in core.rules().sets[name].tiers), default=count),
             'tiers': [{'pieces': t.pieces, 'active': count >= t.pieces,
                        'descriptions': [core.rules().effects[e].desc for e in t.effects]}
                       for t in core.rules().sets[name].tiers]}
            for name, count in counts.items() if name in core.rules().sets]
    return {**asdict(base), "stats": dict(spec.panel), "stat_meta": stat_meta(), "damage_label": panel.damage_label(spec),
            "base_stats": dict(spec.base), "stat_bonus": {k: v - spec.base.get(k, 0) for k, v in spec.panel.items()}, "set_details": sets,
            "pity": await economy.get_pity(openid), "sets": counts,
            "cards": await economy.active_sponsor_cards(openid), "capacity": await economy.max_item_kinds(openid)}


async def inventory(openid: str) -> dict:
    if not await economy.user_exists(openid):
        raise GameError("no_user")
    return {"capacity": await economy.max_item_kinds(openid), "items": [
        {"index": n, "name": name, "quantity": qty, "enhance": level, "temper": temper,
         "slot": core.item_slot(name), "item_id": core.item_by_name(name).id}
        for n, (name, qty, level, temper) in enumerate(await bag.list_inventory(openid), 1)]}


async def _admin_one(openid: str, body: AdminAction) -> Any:
    action, amount = body.action, body.quantity
    resources = {"coins": (economy.add_coins, economy.remove_coins),
                 "world_coins": (economy.add_world_coins, economy.remove_world_coins),
                 "stamina": (economy.add_stamina, economy.remove_stamina),
                 "exp": (economy.add_exp, economy.remove_exp), "pity": (economy.add_pity, economy.remove_pity)}
    if action in resources:
        add, remove = resources[action]
        if body.remove_all:
            return checked(await remove(openid, None))
        if amount is None or amount == 0:
            raise GameError("bad_qty")
        result = await (add(openid, amount) if amount > 0 else remove(openid, -amount))
        if isinstance(result, tuple):
            if not result[0]:
                raise GameError(result[1] or "invalid")
            return {"current": result[2]}
        return checked(result)
    if action == "tower":
        if not await sponsor.add_tower_free(openid, positive(amount)):
            raise GameError("no_user")
        return {"bonus": await tower.tower_free_bonus(openid)}
    if action in ("item", "items"):
        name = core.item_name(int(body.name)) if body.name.isdigit() else body.name
        names = [name] if action == "item" else [core.item_name(i) for i in body.item_ids]
        if not names or not all(names):
            raise GameError("no_item")
        return [checked(await bag.add_item(openid, name, positive(amount, 1))) for name in names]
    if action == "remove_item":
        return checked(await bag.remove_item(openid, body.name, None if body.remove_all else positive(amount), body.enhance_level))
    if action == "destroy_equipped":
        return checked(await bag.destroy_equipped(openid, slot_of(body.slot or "")))
    if action == "prop":
        return checked(await props.grant_prop(openid, body.name, positive(amount, 1)))
    if action == "remove_prop":
        return checked(await props.remove_prop(openid, body.name, None if body.remove_all else positive(amount)))
    if action == "makeup":
        return checked(await checkin.makeup_checkin(openid, amount))
    if action == "force":
        if not await economy.user_exists(openid):
            raise GameError("no_user")
        (info.force_boss_hidden if body.enabled else info.clear_boss_hidden)(openid)
        return {"enabled": body.enabled}
    if action == "card":
        if body.kind is None:
            raise GameError("invalid")
        ok, error, text = await sponsor.grant_card(openid, body.kind)
        if not ok:
            raise GameError(error or "invalid")
        return {"text": text}
    if action == "gem":
        if not body.name or not body.features:
            raise GameError("invalid")
        flags = {key: key in body.features for key in sponsor.FEATURE_LABEL}
        ok, error, text = await sponsor.grant_named_gem(openid, body.name, flags)
        if not ok:
            raise GameError(error or "invalid")
        return {"text": text}
    raise GameError("invalid")


async def admin_action(body: AdminAction) -> dict:
    if body.action == "festival":
        if body.enabled:
            if body.name != props.FRAGMENT_NAME and core.item_by_name(body.name) is None:
                raise GameError("no_item")
            info.set_festival(body.name, positive(body.quantity))
        else:
            info.clear_festival()
        return {"enabled": body.enabled, "name": body.name, "quantity": body.quantity}
    if body.action == "redeem_code":
        return asdict(checked(await props.create_redeem_code(body.name, positive(body.quantity, 1), easter_codes())))
    if body.action == "remove_gem":
        ok, error, text = await sponsor.remove_named_gem(body.name)
        if not ok:
            raise GameError(error or "invalid")
        return {"text": text}
    if body.all_players and body.action in ("force", "gem"):
        raise GameError("invalid", "请指定玩家，不支持全服")
    targets = await economy.list_user_qqs() if body.all_players else body.targets
    if not targets or (body.action == "gem" and len(targets) != 1):
        raise GameError("invalid", "请指定目标玩家")
    results = []
    for target in dict.fromkeys(targets):
        openid = target if await economy.user_exists(target) else (await economy.openid_by_user_id(target) or target)
        try:
            async with core.tx():
                result = await _admin_one(openid, body)
            results.append({"openid": openid, "ok": True, "data": result})
        except GameError as exc:
            results.append({"openid": openid, "ok": False, "error": {"code": exc.code, "message": exc.message}})
    return {"results": results}


async def dispatch(key: str, openid: str, path: dict, query: dict, body: RequestBody | None, superuser: bool) -> Any:
    if key == "panel":
        return await player_panel(openid)
    if key == "profile_sync":
        account = await economy.touch_account(openid, body.user_id, body.name)
        if body.group_id:
            await economy.remember_group(body.group_id)
        return account
    if key == "profile":
        row = await Account.get_or_none(openid=openid)
        if row is None:
            raise GameError("not_found")
        return {"openid": row.openid, "user_id": row.user_id, "name": row.name, "created_at": int(row.created_at.timestamp())}
    if key == "checkin":
        result = await checkin.checkin(openid)
        bonus = await sponsor.checkin_bonus(openid) if not result.already_today else None
        return {**asdict(result), "bonus": bonus}
    if key == "makeup":
        return checked(await checkin.makeup_checkin(openid, body.days))
    if key in ("bag", "sort"):
        if key == "sort" and await bag.sort_inventory(openid) is None:
            raise GameError("no_user")
        return await inventory(openid)
    if key == "bag_detail":
        row = await bag.inventory_at(openid, positive(path["index"]))
        if row is None:
            raise GameError("no_item")
        return {**await owned_item(row[0], row[2], row[3]), "quantity": row[1]}
    if key == "equipped":
        row = await bag.get_equipped(openid, slot_of(path["slot"]))
        if row is None:
            raise GameError("empty")
        return await owned_item(*row)
    if key == "equip":
        row = await bag.inventory_at(openid, body.index)
        if row is None:
            raise GameError("no_item")
        name, _, level, temper = row
        return checked(await bag.equip_item(openid, core.item_slot(name), name, level, temper))
    if key == "unequip":
        return checked(await bag.unequip_slot(openid, body.slot))
    if key == "enhance_preview":
        result = await enhance.enhance_preview(openid, slot_of(query.get("slot", "")))
        if result is None:
            raise GameError("empty")
        return result
    if key == "enhance":
        preview = await enhance.enhance_preview(openid, body.slot)
        if preview is not None and ((body.expected_level is not None and preview.level != body.expected_level)
                                    or (body.expected_name is not None and preview.name != body.expected_name)):
            raise GameError("conflict", "装备或强化等级已变化，请重新确认")
        if preview is not None and (preview.level >= 10 or preview.chance < 1) and body.target is None and (not body.confirmed or body.expected_level is None or body.expected_name is None):
            raise GameError("confirm", "请确认本次强化", **asdict(preview))
        return checked(await enhance.enhance(openid, body.slot, body.target))
    if key == "temper":
        result, plan = await enhance.temper(openid, body.slot)
        return {**asdict(checked(result)), "plan": plan, "temper_cap": tuning.value('temper_cap_pct')}
    if key == "sell":
        result = checked(await bag.sell(openid, body.index, body.quantity))
        item = core.item_by_name(result.name)
        return {**asdict(result), "price": item.price if item else 0, "refund": info.enhance_refund(result.enhance)}
    if key == "sell_many":
        return checked(await bag.sell_many(openid, body.indices))
    if key == "decompose":
        return checked(await bag.decompose_inventory_at(openid, body.index, body.quantity))
    if key == "craft":
        result = checked(await bag.craft_recipe(openid, body.recipe_id))
        return {**asdict(result), "inputs": [i.model_dump() for i in core.rules().recipes[body.recipe_id].inputs]}
    if key == "expand":
        return checked(await bag.expand_bag_at(openid, body.index))
    if key == "warehouse":
        if not await economy.user_exists(openid):
            raise GameError("no_user")
        return await props.list_warehouse(openid)
    if key == "prop_use":
        effect = await props.prop_effect(openid, body.key)
        quantity, choice = body.quantity, body.choice
        if body.argument is not None:
            if body.argument.isdigit() and effect not in ("boss_choice", "dungeon_lure", "dungeon_cross"):
                quantity, choice = positive(body.argument), ""
                if quantity > 1_000_000:
                    raise GameError("bad_qty")
            else:
                quantity, choice = 1, body.argument
        result = checked(await props.use_prop(openid, body.key, quantity, choice))
        battle = checked(await dungeon.cross_challenge(openid, choice)) if effect == "dungeon_cross" else None
        return {**asdict(result), "battle": battle}
    if key == "prop_craft":
        return checked(await props.craft_prop(openid, body.name, body.quantity))
    if key == "redeem":
        return checked(await props.redeem_code(openid, body.code, easter_codes()))
    if key == "shop_buy":
        fn = props.buy_gift_box if body.kind == "box" else props.buy_world_prop
        return checked(await fn(openid, body.index, body.quantity))
    if key == "dungeon":
        return checked(await dungeon.challenge(openid, positive(path["id"])))
    if key == "tower_status":
        status, stamina, used = await tower.tower_status(openid)
        return {"status": status, "stamina": stamina, "used": used, "bonus": await tower.tower_free_bonus(openid)}
    if key == "tower":
        result = await tower.climb(openid, confirmed=body.confirmed)
        if not result.ok and result.error == 'confirm':
            raise GameError('confirm', used=result.used, stamina=result.stamina, cost=tuning.value('tower_extra_stamina'))
        return {**asdict(checked(result)), 'cost': tuning.value('tower_extra_stamina') if result.paid else 0}
    if key == "boss_status":
        if not await economy.user_exists(openid):
            raise GameError("no_user")
        status = await world_boss.world_boss_status(openid)
        return {**asdict(status), "limit": tuning.value('world_boss_daily_limit'),
                "cooldown_left": max(0, tuning.value('world_boss_cooldown') - int(core.now() - status.last_time))}
    if key == "boss":
        result = checked(await world_boss.challenge(openid, superuser=superuser))
        return {**asdict(result), "remaining_attempts": max(0, tuning.value('world_boss_daily_limit') - result.record.used),
                "cooldown": tuning.value('world_boss_cooldown'), "rules": boss_rules()}
    if key == "rank":
        try:
            day = date.fromisoformat(query["day"]) if query.get("day") else core.today()
        except ValueError as exc:
            raise GameError("invalid", "日期格式应为 YYYY-MM-DD") from exc
        rows = await world_boss.world_boss_rank(day, min(100, positive(query.get("limit"), tuning.value('world_boss_top_n'))))
        items = [{"openid": owner, "name": await economy.account_name(openid=owner) or owner, "damage": damage} for owner, damage in rows]
        return {"items": items, "rules": boss_rules()} if query.get('with_rules') == 'true' else items
    if key in ("market", "market_detail"):
        rows = await market.list_market()
        if key == "market":
            return {"items": rows, "rules": {"fee_percent": tuning.value('market_fee_percent'),
                    "list_limit": tuning.value('market_list_limit')}} if query.get('with_rules') == 'true' else rows
        result = next((row for row in rows if row.id == positive(path["id"])), None)
        if result is None:
            raise GameError("no_listing")
        listing = await MarketListing.get(id=result.id)
        return {**asdict(result), "temper": listing.temper,
                "equipment": await owned_item(result.name, result.enhance, listing.temper)}
    if key == "listing":
        return checked(await market.list_on_market(openid, body.index, body.quantity, body.unit_price))
    if key == "buy":
        return checked(await market.buy_listing(openid, positive(path["id"]), body.quantity))
    if key == "cancel":
        return checked(await market.cancel_listing(openid, positive(path["id"])))
    if key in ("dungeons", "dungeon_guide"):
        kwargs = {"pity": await economy.get_pity(openid)}
        gem = await sponsor.equipped_gem(openid)
        kwargs["gem_pity"] = bool(gem and gem.pity)
        result = info.dungeon_list(**kwargs) if key == "dungeons" else info.dungeon_guide(positive(path["id"]), **kwargs)
        if result is None:
            raise GameError("no_dungeon")
        return result
    if key == "item":
        item_id = int(path["id"])
        if core.item(item_id) is None:
            raise GameError("no_item")
        return item_detail(core.rules(), item_id)
    if key == "set":
        spec = core.rules().sets.get(path["name"])
        if spec is None:
            raise GameError("not_found")
        return {"set": spec, "items": [i for i in core.rules().items.values() if path["name"] in i.sets]}
    if key == "recipes":
        return list(core.rules().recipes.values())
    if key == "prop_recipes":
        return props.list_prop_recipes()
    if key == "shop":
        boxes = []
        for d in info.sorted_dungeons():
            box = props.find_gift_box(d.name)
            if box is not None:
                boxes.append({"id": d.id, "name": box.name, "dungeon": d.name, "price": box.value, "level": d.id * 5 + 2})
        wallet = await economy.get_panel(openid)
        return {"boxes": boxes, "world_coins": wallet.world_coins if wallet else 0,
                "world": [{"id": n, "name": name, "price": tuning.value('world_shop_price')} for n, name in enumerate(tuning.value('world_shop_items'), 1)]}
    if key == "admin_users":
        return await economy.list_users()
    if key == "admin_action":
        return await admin_action(body)
    if key == "announcement":
        return {"sent": await economy.announcement_sent(path["version"], positive(path["group_id"]))}
    if key == "announcement_mark":
        await economy.mark_announcement(body.version, body.group_id)
        return {"sent": True}
    raise GameError("not_found")


async def execute(operation: Operation, actor: str, superuser: bool, path: dict, query: dict,
                  body: RequestBody | None, request_id: str = "") -> Any:
    if operation.admin and not superuser:
        raise GameError("forbidden")
    openid = path.get("openid", actor)
    if openid != actor and not operation.admin:
        raise GameError("forbidden", "只能操作自己的角色")
    payload = body.model_dump(mode="json") if body else {}
    fingerprint = hashlib.sha256(json.dumps([operation.key, path, query, payload, superuser], sort_keys=True, ensure_ascii=False).encode()).hexdigest()
    key = hashlib.sha256(f"{actor}\0{request_id}".encode()).hexdigest()
    write = operation.method != "GET"
    # 运行时开关和冷却也跟随失败回滚，避免数据库恢复后仍被冷却锁住。
    changes_rules = operation.key == "admin_action" and body.action in ("gem", "remove_gem")
    async with (core.rules_tx() if changes_rules else core.tx()):
        if write and request_id:
            receipt = await CommandReceipt.get_or_none(key=key)
            if receipt:
                if receipt.fingerprint != fingerprint:
                    raise GameError("conflict", "同一个请求编号不能用于不同操作")
                return receipt.result
        source = 'admin_' + body.action if operation.key == 'admin_action' else operation.key
        recording = write and operation.key != 'announcement_mark'
        with ledger.operation(source, actor, key if request_id else '') if recording else nullcontext():
            data = jsonable_encoder(await dispatch(operation.key, openid, path, query, body, superuser))
            if recording:
                await ledger.completed(operation.key, openid, data)
        if operation.admin:
            await GameAudit.create(actor=actor, action=operation.key, detail={"path": path, "request": payload, "result": data})
        if write and request_id:
            await CommandReceipt.create(key=key, fingerprint=fingerprint, result=data)
        return data
