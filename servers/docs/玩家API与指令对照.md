# 玩家 API 与指令对照

本表从源项目的玩家接口与机器人指令说明整理，适用于当前后端与 NoneBot 代码。共享 `OPERATIONS` 定义 46 个玩家/管理/机器人 HTTP 操作；机器人另有本地帮助与战报缓存指令。这里描述代码入口，不表示已完成真实 QQ 收发验收。

Vue 网站与旧项目的完整持久化数据已迁入；goqbot 程序由使用者按系统和 CPU 架构提供，程序及运行数据不提交 Git。
源项目的独立集成验收工具没有迁入，实际运行边界见 [架构与迁移范围](架构与迁移范围.md)。本文件只列玩家与机器人相关操作，网站账号、规则管理、统计及模拟接口以 API 当前 `/openapi.json` 为准。

## 调用约定

- 下表玩家路径统一加 `/api/v1`。机器人使用 Bearer bot 令牌（`player` scope）和 `X-Player-Openid`；普通调用只能操作本人。
- 超管指令先由 NoneBot `SUPERUSER` 校验，再经可信 bot 令牌传递 `X-Actor-Superuser: true`；sim 令牌不能代理玩家或伪造超管身份。
- 写操作使用 `Idempotency-Key`：重复请求返回原结果，同一个编号更换参数返回 409。价格、伤害、奖励均由逻辑服务计算。
- 返回统一 `ApiResponse`。请求模型禁止额外字段，响应类型见共享契约；道具编号/背包序号为 1 起，规则物品 ID 允许 0。
- `rank` 支持 `day=YYYY-MM-DD`、`limit`（最多 100）；强化预览使用 `slot`。强化二次确认检查装备名称和等级；聊天消息重发不充当确认。

## 全部玩家、管理和机器人 API

| 操作键 | 方法和路径 | 用途 | 机器人调用／未调用原因 |
| --- | --- | --- | --- |
| `panel` | `GET /players/{openid}` | 玩家面板 | 已使用：面板 |
| `profile` | `GET /players/{openid}/profile` | 个人信息 | 已使用：个人信息 |
| `profile_sync` | `POST /players/{openid}/profile` | 同步账号和群 | 已使用：每条游戏指令自动同步账号/群 |
| `checkin` | `POST /players/{openid}/checkin` | 签到及卡片奖励 | 已使用：签到 |
| `makeup` | `POST /players/{openid}/checkin/makeup` | 超管补签（超管） | 未直接使用：已实现，机器人补签统一走 admin_action（action=makeup） |
| `bag` | `GET /players/{openid}/bag` | 背包 | 已使用：背包 |
| `bag_detail` | `GET /players/{openid}/bag/{index}` | 背包装备详情 | 已使用：装备详情 |
| `equipped` | `GET /players/{openid}/equipped/{slot}` | 已穿装备详情 | 已使用：查看 |
| `sort` | `POST /players/{openid}/bag/sort` | 整理背包 | 已使用：整理背包 |
| `equip` | `POST /players/{openid}/equip` | 穿戴 | 已使用：装备 |
| `unequip` | `POST /players/{openid}/unequip` | 卸下 | 已使用：卸下 |
| `enhance_preview` | `GET /players/{openid}/enhance/preview` | 强化预览 | 未直接使用：已实现，机器人使用强化接口返回的 confirm 预览 |
| `enhance` | `POST /players/{openid}/enhance` | 强化 | 已使用：强化 |
| `temper` | `POST /players/{openid}/temper` | 淬炼 | 已使用：淬炼 |
| `sell` | `POST /players/{openid}/sell` | 出售 | 已使用：出售 |
| `sell_many` | `POST /players/{openid}/sell/batch` | 批量出售 | 已使用：批量出售 |
| `decompose` | `POST /players/{openid}/decompose` | 分解 | 已使用：分解 |
| `craft` | `POST /players/{openid}/craft` | 装备合成 | 已使用：合成 |
| `expand` | `POST /players/{openid}/expand` | 背包扩容 | 已使用：背包扩容 |
| `warehouse` | `GET /players/{openid}/warehouse` | 道具仓库 | 已使用：仓库 |
| `prop_use` | `POST /players/{openid}/props/use` | 使用道具及跨界挑战 | 已使用：使用 |
| `prop_craft` | `POST /players/{openid}/props/craft` | 道具合成 | 已使用：道具合成 |
| `redeem` | `POST /players/{openid}/props/redeem` | 兑换码 | 已使用：兑换 |
| `shop_buy` | `POST /players/{openid}/shop/buy` | 商城购买 | 已使用：商城 |
| `dungeon` | `POST /players/{openid}/dungeons/{id}/challenge` | 副本挑战 | 已使用：副本 |
| `tower_status` | `GET /players/{openid}/tower` | 爬塔次数和费用 | 未直接使用：已实现，机器人使用爬塔接口返回的状态/确认 |
| `tower` | `POST /players/{openid}/tower` | 爬塔 | 已使用：爬塔 |
| `boss_status` | `GET /players/{openid}/world-boss` | 世界 BOSS 次数和冷却 | 未直接使用：已实现，机器人直接挑战，失败返回次数/冷却 |
| `boss` | `POST /players/{openid}/world-boss` | 世界 BOSS 挑战 | 已使用：世界BOSS |
| `rank` | `GET /world-boss/rank` | 世界排行榜 | 已使用：世界排行榜 |
| `market` | `GET /market` | 玩家市场 | 已使用：市场 |
| `market_detail` | `GET /market/{id}` | 挂单详情 | 已使用：详情 |
| `listing` | `POST /market` | 上架 | 已使用：上架 |
| `buy` | `POST /market/{id}/buy` | 购买挂单 | 已使用：购买 |
| `cancel` | `DELETE /market/{id}` | 下架挂单 | 已使用：下架 |
| `dungeons` | `GET /dungeons` | 副本列表 | 已使用：副本（无参数） |
| `dungeon_guide` | `GET /dungeons/{id}` | 副本图鉴 | 已使用：副本图鉴 |
| `item` | `GET /items/{id}` | 物品图鉴 | 未直接使用：已实现，当前没有独立物品图鉴聊天指令；网站用 catalog/items |
| `set` | `GET /sets/{name}` | 套装图鉴 | 未直接使用：已实现，当前没有独立套装图鉴聊天指令 |
| `recipes` | `GET /recipes` | 装备配方 | 已使用：合成（无参数） |
| `prop_recipes` | `GET /props/recipes` | 道具配方 | 已使用：道具合成（无参数） |
| `shop` | `GET /shop` | 商城商品和价格 | 已使用：商城 土罐／世界币（不带商品编号） |
| `admin_users` | `GET /admin/players` | 超管用户列表（超管） | 已使用：用户列表 |
| `admin_action` | `POST /admin/players/actions` | 超管操作（超管） | 已使用：给代币、给世界币、给体力、给经验、给保底、给爬塔、给物品、批量给物品、删除物品、删除装备、给道具、删除道具、生成兑换码、补签、必遇、节日福利、给周卡、给月卡、给年卡、定制宝石、删除定制宝石 |
| `announcement` | `GET /bot/announcements/{version}/{group_id}` | 公告发送记录 | 兼容保留：自动公告插件已移除 |
| `announcement_mark` | `POST /bot/announcements` | 记录公告发送 | 兼容保留：自动公告插件已移除 |

六条“未直接使用”的 API 已有服务端实现，只是未由当前机器人指令直接调用。公告两个接口仅作兼容保留，当前 NoneBot 已移除自动公告插件，也没有对应聊天指令。

## 全部机器人指令与别名

指令前缀沿用 NoneBot 的 `COMMAND_START` 配置，帮助与按钮会自动带前缀；示例配置使用 `/`、`.`、`。`，例如 `/整理背包`。下表写主触发词；尖括号为必填，方括号为可选。管理员目标支持 openid、已同步的 QQ user_id、@玩家；支持的批量操作可用“全服”。

| 主指令及参数 | 别名 | 权限 | 操作键／入口 | 功能组 | 调用示例 | 显式处理函数 |
| --- | --- | --- | --- | --- | --- | --- |
| `签到` | `打卡` | 玩家 | `checkin` | 角色 | `/签到` | `role.handle_checkin` |
| `面板` | — | 玩家 | `panel` | 角色 | `/面板` | `role.handle_panel` |
| `个人信息` | — | 玩家 | `profile` | 角色 | `/个人信息` | `role.handle_profile` |
| `背包` | — | 玩家 | `bag` | 背包装备 | `/背包` | `inventory.handle_bag` |
| `整理背包` | — | 玩家 | `sort` | 背包装备 | `/整理背包` | `inventory.handle_sort_bag` |
| `查看 <部位>` | `查看武器`、`查看护甲`、`查看手镯`、`查看项链`、`查看宝石` | 玩家 | `equipped` | 背包装备 | `/查看 武器` | `inventory.handle_view_equipped` |
| `装备详情 <背包序号>` | — | 玩家 | `bag_detail` | 背包装备 | `/装备详情 1` | `inventory.handle_bag_detail` |
| `装备 <背包序号>` | — | 玩家 | `equip` | 背包装备 | `/装备 1` | `inventory.handle_equip` |
| `卸下 <部位>` | — | 玩家 | `unequip` | 背包装备 | `/卸下 武器` | `inventory.handle_unequip` |
| `强化 <部位> [目标等级]` | `强化武器`、`强化护甲`、`强化手镯`、`强化项链` | 玩家 | `enhance` | 背包装备 | `/强化 武器` | `inventory.handle_enhance` |
| `淬炼 <部位>` | `淬炼武器`、`淬炼护甲`、`淬炼手镯`、`淬炼项链` | 玩家 | `temper` | 背包装备 | `/淬炼 武器` | `inventory.handle_temper` |
| `出售 <背包序号> [数量]` | — | 玩家 | `sell` | 背包装备 | `/出售 1 2` | `inventory.handle_sell` |
| `批量出售 <背包序号> <背包序号> ...` | — | 玩家 | `sell_many` | 背包装备 | `/批量出售 1 2` | `inventory.handle_sell_many` |
| `分解 <背包序号> [数量]` | — | 玩家 | `decompose` | 背包装备 | `/分解 1` | `inventory.handle_decompose` |
| `背包扩容 <背包序号>` | — | 玩家 | `expand` | 背包装备 | `/背包扩容 1` | `inventory.handle_expand_bag` |
| `合成 [配方编号]` | — | 玩家 | `craft`；查询入口 `recipes` | 背包装备 | `/合成 1` | `inventory.handle_craft` |
| `仓库` | — | 玩家 | `warehouse` | 背包装备 | `/仓库` | `inventory.handle_warehouse` |
| `使用 <编号> [数量或选择]` | — | 玩家 | `prop_use` | 道具商城 | `/使用 1` | `items.handle_use_prop` |
| `道具合成 [产物名称] [数量]` | — | 玩家 | `prop_craft`；查询入口 `prop_recipes` | 道具商城 | `/道具合成 小礼盒` | `items.handle_craft_prop` |
| `商城 土罐 [副本编号] [数量] / 世界币 [编号] [数量]` | — | 玩家 | `shop_buy`；查询入口 `shop` | 道具商城 | `/商城 世界币 1` | `items.handle_shop` |
| `兑换 <兑换码>` | — | 玩家 | `redeem` | 道具商城 | `/兑换 abc` | `items.handle_redeem` |
| `兑换码` | — | 玩家 | `redeem_help`（本地帮助/战报缓存） | 道具商城 | `/兑换码` | `items.handle_redeem_help` |
| `副本 [编号]` | — | 玩家 | `dungeon`；查询入口 `dungeons` | 战斗战报 | `/副本 1` | `battle.handle_dungeon` |
| `副本图鉴 <编号>` | — | 玩家 | `dungeon_guide` | 战斗战报 | `/副本图鉴 1` | `battle.handle_dungeon_guide` |
| `战报详情 [页码]` | — | 玩家 | `battle_detail`（当前战报缓存；无参数第一页，连续详情会话可指定页码） | 战斗战报 | `/战报详情` 或 `/战报详情 3` | `battle.handle_battle_detail` |
| `爬塔` | — | 玩家 | `tower` | 战斗战报 | `/爬塔` | `battle.handle_tower` |
| `世界BOSS` | `世界boss` | 玩家 | `boss` | 战斗战报 | `/世界BOSS` | `battle.handle_world_boss` |
| `世界排行榜` | — | 玩家 | `rank` | 战斗战报 | `/世界排行榜` | `battle.handle_world_rank` |
| `市场` | — | 玩家 | `market` | 市场交易 | `/市场` | `market.handle_market` |
| `详情 <挂单编号>` | — | 玩家 | `market_detail` | 市场交易 | `/详情 1` | `market.handle_listing_detail` |
| `上架 <背包序号> [数量] <单价>` | — | 玩家 | `listing` | 市场交易 | `/上架 1 100` | `market.handle_create_listing` |
| `购买 <挂单编号> [数量]` | — | 玩家 | `buy` | 市场交易 | `/购买 1` | `market.handle_buy` |
| `下架 <挂单编号>` | — | 玩家 | `cancel` | 市场交易 | `/下架 1` | `market.handle_cancel_listing` |
| `帮助` | `菜单`、`help` | 玩家 | `help`（本地帮助/战报缓存） | 帮助菜单 | `/帮助` 或 `/帮助?` | `menus.handle_help_menu` |
| `背包菜单` | — | 玩家 | `bag_help`（本地帮助/战报缓存） | 帮助菜单 | `/背包菜单` | `menus.handle_bag_menu` |
| `超管菜单` | — | 超管 | `admin_help`（本地帮助/战报缓存） | 管理员 | `/超管菜单` | `admin.handle_admin_menu` |
| `给代币 <目标> <数量或-全部>` | — | 超管 | `admin_action`，`action=coins` | 管理员 | `/给代币 <玩家> 10` | `admin.handle_grant_coins` |
| `给世界币 <目标> <数量或-全部>` | — | 超管 | `admin_action`，`action=world_coins` | 管理员 | `/给世界币 <玩家> -全部` | `admin.handle_grant_world_coins` |
| `给体力 <目标> <数量或-全部>` | — | 超管 | `admin_action`，`action=stamina` | 管理员 | `/给体力 <玩家> 10` | `admin.handle_grant_stamina` |
| `给经验 <目标> <数量或-全部>` | — | 超管 | `admin_action`，`action=exp` | 管理员 | `/给经验 <玩家> 10` | `admin.handle_grant_exp` |
| `给保底 <目标> <数量或-全部>` | — | 超管 | `admin_action`，`action=pity` | 管理员 | `/给保底 <玩家> 10` | `admin.handle_grant_pity` |
| `给爬塔 <目标> <数量>` | `给爬塔次数` | 超管 | `admin_action`，`action=tower` | 管理员 | `/给爬塔 <玩家> 1` | `admin.handle_grant_tower` |
| `给物品 <目标> <物品名或编号> [数量]` | — | 超管 | `admin_action`，`action=item` | 管理员 | `/给物品 <玩家> 0 1` | `admin.handle_grant_item` |
| `批量给物品 <目标> <编号> <编号> ...` | — | 超管 | `admin_action`，`action=items` | 管理员 | `/批量给物品 <玩家> 0 1` | `admin.handle_grant_items` |
| `删除物品 <目标> <名称> [+强化等级] [数量或全部]` | `删物品` | 超管 | `admin_action`，`action=remove_item` | 管理员 | `/删除物品 <玩家> 生锈铁剑 +2 全部` | `admin.handle_remove_item` |
| `删除装备 <目标> <部位>` | `删装备` | 超管 | `admin_action`，`action=destroy_equipped` | 管理员 | `/删除装备 <玩家> 武器` | `admin.handle_remove_equipped` |
| `给道具 <目标> <名称> [数量]` | — | 超管 | `admin_action`，`action=prop` | 管理员 | `/给道具 <玩家> 体力药（中） 1` | `admin.handle_grant_prop` |
| `删除道具 <目标> <名称> [数量或全部]` | `删道具` | 超管 | `admin_action`，`action=remove_prop` | 管理员 | `/删除道具 <玩家> 体力药（中） 1` | `admin.handle_remove_prop` |
| `生成兑换码 <名称> [数量]` | — | 超管 | `admin_action`，`action=redeem_code` | 管理员 | `/生成兑换码 体力药（中）` | `admin.handle_create_redeem_code` |
| `补签 <目标> [天数或全部]` | — | 超管 | `admin_action`，`action=makeup` | 管理员 | `/补签 <玩家> 全部` | `admin.handle_makeup_checkin` |
| `必遇 [关闭] <目标>` | — | 超管 | `admin_action`，`action=force` | 管理员 | `/必遇 关闭 <玩家>` | `admin.handle_force_boss` |
| `节日福利 <物品名> <数量> / 关闭` | — | 超管 | `admin_action`，`action=festival` | 管理员 | `/节日福利 礼盒碎片 1` | `admin.handle_festival` |
| `用户列表` | — | 超管 | `admin_users` | 管理员 | `/用户列表` | `admin.handle_list_users` |
| `给周卡 <目标>` | — | 超管 | `admin_action`，`action=card`，`kind=week` | 管理员 | `/给周卡 <玩家>` | `admin.handle_grant_week_card` |
| `给月卡 <目标>` | — | 超管 | `admin_action`，`action=card`，`kind=month` | 管理员 | `/给月卡 <玩家>` | `admin.handle_grant_month_card` |
| `给年卡 <目标>` | — | 超管 | `admin_action`，`action=card`，`kind=year` | 管理员 | `/给年卡 <玩家>` | `admin.handle_grant_year_card` |
| `定制宝石 <目标> <名称> <功能> ...` | — | 超管 | `admin_action`，`action=gem` | 管理员 | `/定制宝石 <玩家> 测试宝石 保底` | `admin.handle_custom_gem` |
| `删除定制宝石 <名称>` | — | 超管 | `admin_action`，`action=remove_gem` | 管理员 | `/删除定制宝石 测试宝石` | `admin.handle_remove_custom_gem` |
| `爬塔概括` | — | 玩家 | 本次爬塔的缓存概括，无新增 HTTP 操作 | 战斗战报 | `/爬塔概括` | `battle.handle_tower_summary` |
| `爬塔详情 [页码]` | — | 玩家 | 当前爬塔战报；同战报详情的页码与会话校验，无新增 HTTP 操作 | 战斗战报 | `/爬塔详情` 或 `/爬塔详情 3` | `battle.handle_tower_detail` |
| `系统状态` | — | 超管 | `GET /api/v1/system/health` | 系统状态 | `/系统状态` | `status.handle_status` |
| `更新数据` | — | 已退役 | 不注册；规则由后端规则管理接口维护 | 已退役 | — | — |

每条迁移游戏指令还会自动调用 `profile_sync`；“系统状态”保留原独立插件。战报保留 30 分钟，长报告按完整行分页。普通玩家补签通过“使用 补签符”，不开放超管补签权限。

调用示例中的 `<玩家>` 需替换为实际 openid、已同步的 QQ 号或 @玩家；物品序号与名称按当前规则和背包选择。`战报详情 3` 仅在已经打开当前详情且确有第三页时有效。

## 代码核对入口

- [玩家路由与请求契约](../contracts/src/avalon_contracts/api/game.py)、[响应契约](../contracts/src/avalon_contracts/api/game_views.py)。
- [主指令与别名](../../bot/nonebot/src/avalon_bot/commands.py)、[客户端及二次确认](../../bot/nonebot/src/avalon_bot/game_client.py)。
- [游戏操作分发](../logic/src/avalon_logic/game/operations.py)、[机器人测试](../../bot/nonebot/tests/)。

NoneBot 健康接口为 `GET /health` 和 `GET /health/onebot`，无需聊天指令。后者在没有外部协议连接时返回 503。
整套项目由根目录 `uv run main.py` 启动，按 Ctrl+C 停止；没有恢复旧项目的 `avalon-ctl` 启停与状态命令。
