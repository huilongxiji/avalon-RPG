"""后端入口：在 servers 目录运行  uv run app.py  （开发时可以加 --reload，改代码自动重启）

依次做这几件事：
1. 第一次运行时根据 servers/.env.example 生成 servers/.env，并自动填写还没填的令牌；
   按 NoneBot 的 ENVIRONMENT 创建机器人配置，把空白 API 令牌填成后端 bot 令牌
2. 升级数据库表结构（Tortoise 自带的迁移工具）
3. 启动逻辑后端（127.0.0.1:7901，只在本机）→ 等它就绪 → 启动 API 后端（servers/.env 里的地址和端口）

两个后端各占一个进程，各自的数据库连接互不干扰。
按 Ctrl+C 一起停止；其中任何一个意外退出，另一个也会停止。
"""

from __future__ import annotations

import os
import secrets
import shutil
import signal
import subprocess
import sys
import time
import urllib.request
from pathlib import Path

SERVER_DIR = Path(__file__).resolve().parent
ROOT = SERVER_DIR.parent
LOGIC_HEALTH = "http://127.0.0.1:7901/health"
# 访问本机地址不走系统代理
_LOCAL = urllib.request.build_opener(urllib.request.ProxyHandler({}))

TOKEN_KEYS = {
    "AVALON_INTERNAL_TOKEN": "内部令牌（逻辑后端与 API 后端之间用）",
    "AVALON_BOT_TOKEN": "bot 令牌（机器人调用 API 用）",
    "AVALON_SIM_TOKEN": "模拟器令牌（发给使用模拟器的人）",
}
PLACEHOLDER_PREFIX = "请改成"


def init_env(path: Path) -> list[str]:
    """.env 里的令牌空着时生成随机值；已经填过的一律不动，令牌只写进文件，不在屏幕上显示。"""
    if not path.is_file():
        return []
    lines = path.read_text(encoding="utf-8").splitlines()
    seen: set[str] = set()
    notes: list[str] = []
    for i, line in enumerate(lines):
        stripped = line.strip()
        if not stripped or stripped.startswith("#") or "=" not in stripped:
            continue
        key, value = stripped.split("=", 1)
        key, value = key.strip(), value.split(" #", 1)[0].strip()
        if key in TOKEN_KEYS:
            seen.add(key)
            if not value or value.startswith(PLACEHOLDER_PREFIX):
                lines[i] = f"{key}={secrets.token_urlsafe(24)}"
                notes.append(f"已生成 {key}：{TOKEN_KEYS[key]}")
    for key, label in TOKEN_KEYS.items():
        if key not in seen:
            lines.append(f"{key}={secrets.token_urlsafe(24)}")
            notes.append(f"已生成 {key}：{label}")
    if notes:
        path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return notes


def _read_env(path: Path) -> dict[str, str]:
    """只读配置供初始化使用，不把机器人配置写入后端进程环境。"""
    if not path.is_file():
        return {}
    values = {}
    for line in path.read_text(encoding="utf-8").splitlines():
        stripped = line.strip()
        if not stripped or stripped.startswith("#") or "=" not in stripped:
            continue
        key, value = stripped.split("=", 1)
        values[key.strip()] = value.split(" #", 1)[0].strip().strip('"').strip("'")
    return values


def fill_bot_config(root: Path) -> list[str]:
    """初始化独立 NoneBot 配置；保留已经填写的令牌和自定义 API 地址。"""
    bot_dir = root / "bot" / "nonebot"
    environment = os.environ.get("ENVIRONMENT", _read_env(bot_dir / ".env").get("ENVIRONMENT")) or "dev"
    bot_env = bot_dir / f".env.{environment}"
    example = bot_dir / f".env.{environment}.example"
    notes = []
    if not bot_env.is_file() and example.is_file():
        shutil.copyfile(example, bot_env)
        notes.append(f"已生成机器人配置 {bot_env.relative_to(root)}，请填写 OneBot 令牌和管理员。")
    backend = _read_env(root / "servers" / ".env")
    token = backend.get("AVALON_BOT_TOKEN", "")
    if not bot_env.is_file() or not token or token.startswith(PLACEHOLDER_PREFIX):
        return notes
    current = _read_env(bot_env)
    previous = current.get("AVALON_API_TOKEN", "")
    if previous and not previous.startswith(PLACEHOLDER_PREFIX):
        return notes

    updates = {"AVALON_API_TOKEN": token}
    if current.get("AVALON_API_URL", "") in {"", "http://127.0.0.1:7900"}:
        host = backend.get("AVALON_API_HOST") or "127.0.0.1"
        if host in {"0.0.0.0", "::", "[::]"}:
            host = "127.0.0.1"
        if ":" in host and not host.startswith("["):
            host = f"[{host}]"
        port = backend.get("AVALON_API_PORT") or "7900"
        updates["AVALON_API_URL"] = f"http://{host}:{port}"

    lines = bot_env.read_text(encoding="utf-8").splitlines()
    seen = set()
    for i, line in enumerate(lines):
        key = line.split("=", 1)[0].strip()
        if key in updates:
            lines[i] = f"{key}={updates[key]}"
            seen.add(key)
    lines.extend(f"{key}={value}" for key, value in updates.items() if key not in seen)
    bot_env.write_text("\n".join(lines) + "\n", encoding="utf-8")
    notes.append(f"已把 bot 令牌填进机器人配置 {bot_env.relative_to(root)}")
    return notes


def prepare() -> bool:
    env, example = SERVER_DIR / ".env", SERVER_DIR / ".env.example"
    if not env.is_file() and example.is_file():
        shutil.copyfile(example, env)
        print("已根据 .env.example 生成 .env。")
    (ROOT / "data").mkdir(exist_ok=True)

    for note in init_env(env) + fill_bot_config(ROOT):
        print(note)

    from avalon_api.store import migrate as api_migrate
    from avalon_logic.store import migrate as logic_migrate

    print("检查逻辑后端的数据库表结构...")
    if logic_migrate.main() != 0:
        return False
    print("检查 API 后端的数据库表结构...")
    return api_migrate.main() == 0


def wait_ready(proc: subprocess.Popen, url: str, timeout: float = 60) -> bool:
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        if proc.poll() is not None:
            return False
        try:
            with _LOCAL.open(url, timeout=1) as resp:
                if resp.status == 200:
                    return True
        except OSError:
            pass
        time.sleep(0.3)
    return False


def stop(procs: list[subprocess.Popen]) -> None:
    for p in reversed(procs):
        if p.poll() is None:
            p.terminate()
    for p in reversed(procs):
        try:
            p.wait(timeout=10)
        except subprocess.TimeoutExpired:
            p.kill()
            p.wait()


def _ignore_stop_signals() -> None:
    # uv 和编排程序可能重复发送终止信号，清理一旦开始就不能再次被打断。
    for sig in (signal.SIGINT, signal.SIGTERM):
        signal.signal(sig, signal.SIG_IGN)


def _raise_interrupt(*_args) -> None:
    _ignore_stop_signals()
    raise KeyboardInterrupt


def main() -> int:
    os.chdir(SERVER_DIR)
    cache = ROOT / "data" / "cache" / "python"
    sys.pycache_prefix = str(cache)
    os.environ["PYTHONPYCACHEPREFIX"] = str(cache)
    reload = ["--reload"] if "--reload" in sys.argv[1:] else []
    # 编排程序停止后端时发的是 SIGTERM，按 Ctrl+C 同样处理
    signal.signal(signal.SIGTERM, _raise_interrupt)
    signal.signal(signal.SIGINT, _raise_interrupt)
    procs: list[subprocess.Popen] = []
    try:
        if not prepare():
            print("数据库表结构升级失败，请看上面的错误信息。", file=sys.stderr)
            return 1

        print("启动逻辑后端（127.0.0.1:7901）...")
        logic = subprocess.Popen([sys.executable, "-m", "avalon_logic", *reload], cwd=SERVER_DIR)
        procs.append(logic)
        if not wait_ready(logic, LOGIC_HEALTH):
            print("逻辑后端没有启动成功，请看上面的错误信息。", file=sys.stderr)
            return 1

        from avalon_api.config import get_settings

        settings = get_settings()
        print(f"启动 API 后端（{settings.host}:{settings.port}）...")
        procs.append(subprocess.Popen([sys.executable, "-m", "avalon_api", *reload], cwd=SERVER_DIR))

        while all(p.poll() is None for p in procs):
            time.sleep(0.5)
        print("有一个后端退出了，正在停止全部后端。", file=sys.stderr)
        return 1
    except KeyboardInterrupt:
        print("正在停止后端...")
        return 0
    finally:
        _ignore_stop_signals()
        stop(procs)


if __name__ == "__main__":
    raise SystemExit(main())
