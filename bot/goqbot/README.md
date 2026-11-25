# RPG 中的 goqbot

goqbot 使用原生可执行文件，不使用 uv，也没有单独的启动包装脚本。
仓库不绑定操作系统或 CPU 架构，不附带程序文件；使用者自行下载或构建适合本机的版本。

## 安装程序

将所需可执行文件放入 `bot/goqbot/`，并让根 `avalon.toml` 的 `goqbot.binary` 与文件名一致：

| 系统 | 文件名示例 | `goqbot.binary` |
| --- | --- | --- |
| Linux / macOS | `goqbot` | `"goqbot"`（默认） |
| Windows | `goqbot.exe` | `"goqbot.exe"` |
| 保留下载时的文件名 | 对应平台的原文件名 | 填写相同文件名 |

程序必须匹配当前系统和 CPU 架构。Linux/macOS 等 Unix 系统还需执行 `chmod +x bot/goqbot/goqbot`，使用其他文件名时相应调整。
当前本机沿用已迁移的 macOS arm64 程序，文件名为 `goqbot`，仅在本地保留。

## 路径与 Git

- `bot/goqbot/<goqbot.binary>`：使用者提供的程序文件，不提交 Git。
- `bot/goqbot/config/config.yml`：真实运行配置；缺失时首次启动由 goqbot 自动生成，不提交 Git。
- `data/goqbot/<goqbot.binary>`：第一次统一启动时创建的运行副本。
- `data/goqbot/idmap.db`、`logs/`、`plugins/`、`plugin-data/`：运行数据。

`bot/goqbot/` 在 Git 中仅保留本 README，程序、`config/` 中的真实配置及其他本地文件均忽略。
项目不保存 goqbot 配置模板，初始配置由原生程序内置逻辑生成。
数据库文件（`.db`、`.sqlite`、`.sqlite3` 及其 WAL、SHM、journal 等附属文件）和 `data/` 运行数据也不提交。

本机已验证的 goqbot 版本将日志、ID 映射和插件默认路径放在可执行文件目录下，JS 插件数据目录也固定在该目录。
因此只改工作目录或 `-config` 参数不足以归集全部数据。根 `main.py` 保留上述运行副本，使生成的数据留在根 `data`。
启动器仅在副本不存在时复制，不覆盖已有副本或其自更新。配置独立保存在 `bot/goqbot/config/config.yml`，由 `-config` 指定。

## 启动

放好程序后，在根目录执行 `uv run main.py`。若 `bot/goqbot/config/config.yml` 不存在，
启动器先创建配置父目录，再单独启动原生 goqbot，通过 `-config` 指定路径，由程序自动生成配置。
首次配置生成不启动后端或 NoneBot，也不检查旧服务是否占用默认端口。填写生成的配置后再次执行 `uv run main.py`，启动整套服务。
配置已存在时，后端与 NoneBot 就绪后，启动器先精确检查已有实例；确认不存在才启动 goqbot，并通过 `-config` 读取该配置。
`uv run main.py --check` 只检查并提示首次生成步骤，不创建任何配置文件。

建议通过根统一入口启动。直接在 `bot/goqbot` 目录中裸运行程序，会在源码旁生成默认 `config.yml`、数据库及日志，
也不会自动选用 `config/config.yml`。若需独立运行，先确保 API 与 NoneBot 已启动，使用 `data/goqbot` 中的运行副本并显式指定配置。
统一入口已创建运行副本后，可从项目根执行：

```sh
cd data/goqbot
./goqbot -config ../../bot/goqbot/config/config.yml
```

Windows PowerShell 可在同一运行目录使用 `.\goqbot.exe -config ..\..\bot\goqbot\config\config.yml`；自定义程序文件名时相应替换。
尚无运行副本时，将本机程序复制到 `data/goqbot` 后执行以上命令，保留 Unix 执行权限，不另建启动脚本。

正式接入前填写 QQ 凭据，开启对应反向 WS，并核对：

- `onebot.servers[].ws-reverse.universal` 指向 NoneBot，默认 `ws://127.0.0.1:7891/onebot/v11/ws`。
- 同一项的 `access-token` 与 `bot/nonebot/.env.dev`（或当前环境）的 `ONEBOT_ACCESS_TOKEN` 一致。
- `qq.disabled` 与所需连接的 `disabled` 均为 `false`。
- `idmap.path`、`log.path` 使用运行目录内的相对路径；不要指向旧项目的绝对路径。

本机版本可用 `bot/goqbot/goqbot -version` 只读检查版本，该参数不会读取运行配置或连接 QQ。
手动升级时先停止对应实例，再替换运行副本。`idmap.db` 使用 bbolt 格式，不是 SQLite；迁移历史映射需采用一致性备份。

## 运行中管理与自行更新

根 `uv run main.py` 运行期间，可在项目根目录的另一个终端执行：

```sh
uv run main.py status goqbot
uv run main.py status goqbot --json
uv run main.py stop goqbot
uv run main.py start goqbot
uv run main.py restart goqbot
```

`start goqbot` 会按依赖恢复 `backend`（API + Logic）和 `nonebot`；`stop`、`restart` 只作用于 goqbot。
手动停止后保持停止，不会因为健康检查失败而重新启动。若后端或 NoneBot 已手动停止，单独 `restart goqbot` 会等待依赖，
不会替用户恢复它们；可使用 `start goqbot` 明确恢复依赖。这里的 uv 只运行根管理入口，goqbot 仍是原生程序。

下载更新、同步和自行重启由 goqbot 自己完成。启动器只在 `data/goqbot/<文件名>` 不存在时创建运行副本，
不会用 `bot/goqbot` 的旧程序覆盖已经自更新的副本，也不会另写下载或升级流程。
只要接替进程使用同一程序路径及明确的 `-config` 配置路径，即使原父进程退出、接替进程脱离原组，也能继续识别。

| 情况 | 根启动器行为 |
| --- | --- |
| 原进程消失，可能正在自行更新/重启 | 默认等待 120 秒；期间持续精确查找接替进程，不重复启动 |
| 宽限结束，确定没有匹配进程 | 在依赖就绪后按退避间隔重新启动运行副本 |
| 程序仍存活，但 OneBot 连接断开 | 默认等待 300 秒；超时仅显示离线并继续观察，不杀进程、不代为登录 |
| 权限不足、匹配程序没有明确 `-config`、配置参数歧义或存在多个匹配 | 显示需要检查，禁止猜测拉起第二份 |
| 根入口启动前已有精确匹配实例 | 附着观察；Ctrl+C 或 `down` 保留它，显式 `stop`/`restart` 可停止 |

匹配范围限定为当前系统用户、规范化后的精确运行程序路径（或脚本入口）及精确配置路径，不按进程名子串或端口杀进程。
每次停止还会校验 PID 和创建时间，防止 PID 被其他进程复用；已记录后代按身份清理，无法确认归属时报告错误，不盲目结束陌生进程组。
OneBot 健康检查说明与 NoneBot 的连接是否建立，不替代 QQ 平台登录和消息能力的实际验证。
默认宽限值可在根 `avalon.toml` 的 `[launcher]` 中调整，修改后重启根入口生效。

根管理接口只在本机回环地址监听，临时鉴权记录和单实例锁位于忽略提交的 `data/run/`。
旧版根进程需正常停止后重新执行 `uv run main.py` 才能接入；独立后端和 NoneBot 不会因此被接管。
源码监听仅支持 `backend`、`nonebot`，Vue 使用自身 HMR，goqbot 不参与源码监听。

## 数据迁移与本机验证

完整迁移已将源 goqbot 的 bbolt `idmap.db` 和日志放入根 `data/goqbot`，与其他项目数据一起校验并保留源项目以便回退。
现有 `bot/goqbot/config/config.yml` 的 QQ 凭据原样保留，未被源码目录旁的另一份配置覆盖。
误生成的 `bot/goqbot/config.yml`、源码目录旁的数据库与日志已先归档至
`data/backups/full-migration-20261125-031901.tar.gz` 再清理，正式配置位置唯一。

完整迁移阶段的本机验证使用 macOS arm64 的 goqbot 1.14.14，不代表已验证其他系统或架构。
该迁移阶段的完整数据临时副本中，goqbot → NoneBot 建连、后端与 Vue 健康链、数据目录和 Ctrl+C 回收均已通过。
联调使用禁用 QQ 上游的隔离配置，未登录真实 QQ 或发送聊天消息。正式启动仍会使用本机保留的真实凭据。
