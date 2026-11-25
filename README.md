# Avalon RPG

项目已迁入 `avalon_gj` 的后端、NoneBot、Vue 业务源码和完整项目数据，并接入 goqbot 原生程序。
根目录按 `servers`、`bot`、`web`、`sql`、`data` 区分职责；自动公告插件和 `changelog` 目录保持移除。
goqbot 可执行文件由使用者按操作系统和 CPU 架构提供，不随 Git 仓库分发。

```text
avalon-RPG/
├── main.py                  # uv run main.py，统一启动
├── pyproject.toml / uv.lock # 根启动器的独立 uv 项目
├── avalon.toml              # 启动配置和项目根目录标记
├── servers/                # 后端 API、逻辑服务和共享契约
│   ├── app.py              # uv run app.py
│   ├── .env / .env.example # 后端配置
│   ├── api/ / logic/ / contracts/
│   └── tests/ / docs/
├── bot/
│   ├── nonebot/            # uv run bot.py；配置为 .env.dev 或 .env.prod
│   └── goqbot/             # 本机原生程序，不使用 uv
│       └── config/         # config.yml，由 goqbot 首次生成
├── web/                    # Vue 源码、package.json 和 package-lock.json
├── sql/                    # SQL 脚本；私密 SQL 位于忽略提交的 local/
└── data/                   # 数据库、模拟结果、日志、缓存、构建产物和备份
```

## 启动

安装 uv、Node.js 与 npm，并按 [goqbot 说明](bot/goqbot/README.md) 放好适合本机的程序后，在项目根目录执行：

```sh
uv run main.py
```

入口依次启动后端、NoneBot、goqbot 和 Vue。首次运行、前端依赖文件变化或 `web/node_modules` 缺失时，
会先执行 `npm ci` 安装锁定依赖；安装失败时不启动服务。Vue 默认使用 `http://127.0.0.1:5173`，
端口被占用时直接报错，不自动切换端口，统一入口会等待页面就绪。

若 `bot/goqbot/config/config.yml` 不存在，首次执行只启动原生 goqbot 生成配置；
此时不启动其他服务，也不要求旧服务端口空闲。填写生成的配置后再次执行上述命令。
`uv run main.py --check` 只检查，不生成配置或安装前端依赖。
Ctrl+C 或服务异常退出会停止本次启动的整组进程；启动器不会接管或停止其他实例。

各组件也可独立启动：

| 工作目录 | 命令 | 启动内容 |
| --- | --- | --- |
| `servers` | `uv run app.py` | API 与 Logic |
| `bot/nonebot` | `uv run bot.py` | NoneBot，需先启动 API |
| `web` | 首次 `npm ci`，然后 `npm run dev` | Vue 开发服务，需先启动 API |

在 `web` 中执行 `npm run build`，产物写入根 `data/web/dist`，随后可由 API 的默认端口 7900 托管。
goqbot 建议使用统一入口；独立运行须使用 `data/goqbot` 中的运行副本并显式指定配置路径，详见其说明。

根目录、`servers`、`bot/nonebot` 各自使用独立 uv 环境。`uv run` 无需提前激活虚拟环境；
若终端已激活根 `.venv`，进入子项目后出现 `VIRTUAL_ENV ... does not match`，先执行 `deactivate`。
该提示表示 uv 已忽略原环境，并使用当前子项目自己的 `.venv`。后端开发可用 `uv run app.py --reload`。

默认端口为 Logic 7901、API 7900、NoneBot 7891、Vue 5173。正式切换前需自行停止占用这些端口的旧实例。

## 配置

| 组件 | 配置文件 |
| --- | --- |
| 后端 | `servers/.env` |
| NoneBot | `bot/nonebot/.env.dev`；选择 prod 时为 `.env.prod` |
| goqbot | `bot/goqbot/config/config.yml` |
| 统一入口 | 根 `avalon.toml` |

本次迁移保留 RPG 现有后端与 NoneBot 连接配置。后端启动会按配置同步数据库中的服务令牌，
并仅为 NoneBot 的空白 API 令牌填入后端令牌；已有自定义地址、非空令牌和管理员配置保留。
NoneBot 独立入口不直接读取后端私密配置。正式接入 QQ 前核对 `SUPERUSERS`、API 地址与令牌，以及 goqbot 与 NoneBot 的 OneBot 令牌。
Vue 开发代理读取后端地址，前端构建不会把后端私密令牌暴露给浏览器。

goqbot 的 `binary` 默认为 `goqbot`；Windows 可改为 `goqbot.exe`，也可保留下载时的文件名并修改 `avalon.toml`。
Unix 系统需授予执行权限。配置由原生程序生成，项目不保存 goqbot 配置模板。
`bot/goqbot/` 在 Git 中仅保留 README，程序与真实配置均不提交。

## 数据与迁移

完整迁移保留源规则的 13 个版本及原始 ID，其中生效版本为 12、草稿为 13；同时保留 39 名玩家、1 个网站账号和 5 个模拟任务。
这替换了上一阶段仅导入生效规则的临时数据，原 RPG 数据已纳入迁移备份。

| 内容 | RPG 中的位置 |
| --- | --- |
| 规则、玩家、统计、网站账号 | `data/rules.db`、`data/game.db`、`data/stats.db`、`data/api.db` |
| 模拟任务及结果 | `data/sim/` |
| NoneBot 运行数据 | `data/nonebot/` |
| goqbot 运行副本、ID 映射及日志 | `data/goqbot/` |
| 源项目旧日志 | `data/logs/legacy-avalon_gj/` |
| 旧版原始数据与模拟场景 | `data/legacy/old_data/`、`data/legacy/simulator/scenarios/` |
| Python、npm、Vite 等缓存 | `data/cache/` |
| Vue 构建产物 | `data/web/dist/` |
| 迁移前备份 | `data/backups/full-migration-20261125-031901.tar.gz` |

源根 `data` 下的内容在新根 `data` 中保留相对路径。两份私密 SQL 位于 `sql/local/`，不提交 Git。
数据库及其附属文件、运行数据、私密配置和可执行文件均保留在本机，不随代码仓库分发。
源项目保持原样以便回退；备份覆盖目标迁移前的数据、配置及原占位 `web`。

新检出的代码仍可能从空规则库开始。此时世界 BOSS 结算等待规则就绪，不写结算标记；
导入并激活规则、重新加载快照后，后台任务在下一轮恢复。此保护不影响本机已迁入的生效规则。

## 验证

迁移快照中的四个业务 SQLite 数据库及模拟任务库已通过完整性校验。测试使用隔离环境，未连接真实 QQ 或发送聊天消息。
当前数据包含真实玩家和网站账号，测试配置与正式接入配置分开使用。
本轮后端与启动器回归为 264 项通过、35 项旧引擎对拍跳过；Ruff 检查通过。
Vue 依赖安装和生产构建完成，根入口 `--check` 已通过四个组件检查。
完整隔离联调已验证根入口启动、网站及静态资源、API 代理、合成账号登录与 CSRF 校验；Ctrl+C 后全部测试端口释放。
QQ 上游保持关闭，合成账号只写入临时测试副本。本机验收报告位于 `data/migrations/full-migration-smoke-20261125-031901.json`。

```sh
# 从项目根目录运行
uv run --project servers --locked pytest servers -q
uv run --project bot/nonebot --locked pytest bot/nonebot/tests -q

# 从 web 目录运行
npm run typecheck
npm run build
```

[架构与迁移范围](servers/docs/架构与迁移范围.md) ·
[玩家 API 与指令对照](servers/docs/玩家API与指令对照.md) ·
[网站账号管理](servers/docs/网站账号管理.md) ·
[规则管理 API](servers/docs/规则管理.md)
