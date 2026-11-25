"""QQ 机器人入口：在 bot/nonebot 目录运行 uv run bot.py。

配置和插件清单始终读取入口旁的文件；运行目录固定为项目根 data/nonebot。
Python 缓存写入根 data/cache/python，不随调用者的工作目录变化。
"""

import os
import shutil
import sys
from pathlib import Path

BOT_DIR = Path(__file__).resolve().parent
ROOT = BOT_DIR.parents[1]
RUNTIME_DIR = ROOT / "data" / "nonebot"
PYTHON_CACHE = ROOT / "data" / "cache" / "python"

# 在导入第三方和业务模块前归集字节码，并让自动重载的子进程沿用同一路径。
sys.pycache_prefix = str(PYTHON_CACHE)
os.environ["PYTHONPYCACHEPREFIX"] = str(PYTHON_CACHE)
if str(BOT_DIR) not in sys.path:
    sys.path.insert(0, str(BOT_DIR))

import nonebot  # noqa: E402
from nonebot.adapters.onebot.v11 import Adapter as OneBotV11Adapter  # noqa: E402
from nonebot.config import Env  # noqa: E402

environment = Env(_env_file=BOT_DIR / ".env").environment
env_file = BOT_DIR / f".env.{environment}"
example = BOT_DIR / f".env.{environment}.example"
if not env_file.is_file() and example.is_file():
    shutil.copyfile(example, env_file)
    print(f"已生成机器人配置 {env_file.relative_to(ROOT)}，请填写 OneBot 令牌和管理员。")

# NoneBot 内部的 Env() 从工作目录查找 .env，因此显式传递选定环境。
os.environ["ENVIRONMENT"] = environment
RUNTIME_DIR.mkdir(parents=True, exist_ok=True)
os.chdir(RUNTIME_DIR)
nonebot.init(_env_file=(BOT_DIR / ".env", env_file))

driver = nonebot.get_driver()
driver.register_adapter(OneBotV11Adapter)

nonebot.load_from_toml(str(BOT_DIR / "pyproject.toml"))

# 给 NoneBot 的自动重载（.env.dev 里写 FASTAPI_RELOAD=true）用
app = nonebot.get_asgi()

if __name__ == "__main__":
    nonebot.run()
