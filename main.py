"""在项目根目录运行 uv run main.py，依次启动后端、NoneBot 和已配置的可选组件。"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import shutil
import signal
import socket
import subprocess
import sys
import time
import tomllib
import urllib.request
from dataclasses import dataclass
from pathlib import Path
from urllib.parse import urlsplit

ROOT = Path(__file__).resolve().parent
sys.pycache_prefix = str(ROOT / "data" / "cache" / "python")
os.environ["PYTHONPYCACHEPREFIX"] = sys.pycache_prefix
LOCAL = urllib.request.build_opener(urllib.request.ProxyHandler({}))


@dataclass(frozen=True)
class Service:
    name: str
    command: list[str]
    cwd: Path
    health: str = ""
    health_service: str = ""
    binary_source: Path | None = None
    config_path: Path | None = None
    health_kind: str = "json"


def read_env(path: Path) -> dict[str, str]:
    if not path.is_file():
        return {}
    values = {}
    for raw in path.read_text(encoding="utf-8").splitlines():
        line = raw.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        values[key.strip()] = value.split(" #", 1)[0].strip().strip('"').strip("'")
    return values


def health_url(host: str, port: str | int) -> str:
    host = host or "127.0.0.1"
    if host in {"0.0.0.0", "::", "[::]"}:
        host = "127.0.0.1"
    if ":" in host and not host.startswith("["):
        host = f"[{host}]"
    return f"http://{host}:{int(port)}/health"


def configuration(root: Path) -> dict:
    with (root / "avalon.toml").open("rb") as stream:
        return tomllib.load(stream)


def plan(root: Path, *, reload: bool = False) -> tuple[list[Service], list[str]]:
    """只读取文件，不启动进程或生成配置。"""
    cfg = configuration(root)
    uv = shutil.which("uv")
    if not uv:
        raise RuntimeError("没有找到 uv，请先安装 uv 并加入 PATH。")
    servers = root / "servers"
    bot = root / "bot" / "nonebot"
    for entry in (servers / "app.py", bot / "bot.py"):
        if not entry.is_file():
            raise RuntimeError(f"缺少启动入口：{entry.relative_to(root)}")
    backend = {**read_env(servers / ".env.example"), **read_env(servers / ".env")}
    host = os.environ.get("AVALON_API_HOST", backend.get("AVALON_API_HOST")) or "127.0.0.1"
    port = os.environ.get("AVALON_API_PORT", backend.get("AVALON_API_PORT")) or "7900"
    base = read_env(bot / ".env")
    environment = os.environ.get("ENVIRONMENT", base.get("ENVIRONMENT")) or "dev"
    bot_values = {**base, **read_env(bot / f".env.{environment}.example"),
                  **read_env(bot / f".env.{environment}")}
    bot_host = os.environ.get("HOST", bot_values.get("HOST")) or "127.0.0.1"
    bot_port = os.environ.get("PORT", bot_values.get("PORT")) or "7891"
    services = [
        Service("后端", [uv, "run", "--locked", "app.py", *(["--reload"] if reload else [])],
                servers, health_url(host, port), "api"),
        Service("NoneBot", [uv, "run", "--locked", "bot.py"], bot,
                health_url(bot_host, bot_port), "bot"),
    ]
    skipped = []
    goqbot = cfg.get("goqbot", {})
    binary = goqbot.get("binary", "")
    if binary:
        source = (root / "bot" / "goqbot" / binary).resolve()
        if not source.is_relative_to((root / "bot" / "goqbot").resolve()) or not source.is_file():
            raise RuntimeError(
                "请将适合当前系统和 CPU 架构的 goqbot 可执行文件放入 bot/goqbot，"
                "并在 avalon.toml 的 goqbot.binary 中填写文件名。"
            )
        args = goqbot.get("args", [])
        if not isinstance(args, list) or not all(isinstance(arg, str) for arg in args):
            raise RuntimeError("goqbot.args 必须是字符串数组。")
        if any(arg.split("=", 1)[0] in {"-config", "--config"} for arg in args):
            raise RuntimeError("goqbot 配置固定为 bot/goqbot/config/config.yml，不要在 args 中覆盖 -config。")
        runtime = root / "data" / "goqbot"
        config = root / "bot" / "goqbot" / "config" / "config.yml"
        services.append(Service("goqbot", [str(runtime / source.name), "-config", str(config), *args], runtime,
                                binary_source=source, config_path=config))
    else:
        skipped.append("goqbot 未配置可执行文件，本阶段跳过。")
    web = root / "web"
    web_config = cfg.get("web", {})
    if web_config.get("enabled", True) and (web / "package.json").is_file():
        if not (web / "package-lock.json").is_file():
            raise RuntimeError("缺少 web/package-lock.json，无法执行 npm ci；请恢复锁文件后再启动。")
        npm = shutil.which("npm.cmd" if os.name == "nt" else "npm")
        if not npm:
            raise RuntimeError("web/package.json 已存在，但没有找到 npm。")
        web_host = web_config.get("host", "127.0.0.1")
        web_port = int(web_config.get("port", 5173))
        if not isinstance(web_host, str) or not web_host.strip() or not 1 <= web_port <= 65535:
            raise RuntimeError("web.host 必须是监听地址，web.port 必须在 1～65535 之间。")
        services.append(Service("Vue", [npm, "run", "dev", "--", "--host", web_host,
                                        "--port", str(web_port), "--strictPort"], web,
                                health_url(web_host, web_port).removesuffix("health"),
                                health_kind="html"))
    else:
        skipped.append("Vue 尚未迁入或已禁用，本阶段跳过。")
    return services, skipped


def ensure_ports_free(services: list[Service]) -> None:
    urls = ["http://127.0.0.1:7901/health", *(s.health for s in services if s.health)]
    for url in dict.fromkeys(urls):
        address = urlsplit(url)
        try:
            connection = socket.create_connection((address.hostname, address.port), timeout=0.3)
        except OSError:
            continue
        connection.close()
        raise RuntimeError(f"端口 {address.hostname}:{address.port} 已被占用，请先停止对应旧服务。")


def child_environment(root: Path) -> dict[str, str]:
    env = os.environ.copy()
    # 根入口的 uv 环境不能成为另外两个独立项目的环境。
    env.pop("VIRTUAL_ENV", None)
    env.pop("UV_PROJECT_ENVIRONMENT", None)
    env["UV_CACHE_DIR"] = str(root / "data" / "cache" / "uv")
    env["PYTHONPYCACHEPREFIX"] = str(root / "data" / "cache" / "python")
    env["npm_config_cache"] = str(root / "data" / "cache" / "npm")
    return env


def web_install_signature(web: Path) -> dict[str, str | int]:
    return {
        "version": 1,
        "platform": sys.platform,
        **{name: hashlib.sha256((web / name).read_bytes()).hexdigest()
           for name in ("package.json", "package-lock.json")},
    }


def prepare_web_dependencies(root: Path, services: list[Service], env: dict[str, str],
                             processes: list[subprocess.Popen]) -> None:
    service = next((s for s in services if s.name == "Vue"), None)
    if service is None:
        return
    web = service.cwd
    if not web.resolve().is_relative_to(root.resolve()):
        raise RuntimeError("web 目录指向项目外部，已停止安装，避免修改其他项目的依赖。")
    modules = web / "node_modules"
    if modules.is_symlink():
        raise RuntimeError("web/node_modules 是符号链接；请改为该目录内的普通依赖目录后再运行 npm ci。")
    signature = web_install_signature(web)
    stamp = root / "data" / "cache" / "npm" / "web-install.json"
    try:
        installed = json.loads(stamp.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        installed = None
    if modules.is_dir() and installed == signature:
        return
    stamp.parent.mkdir(parents=True, exist_ok=True)
    # npm ci 失败时可能留下部分 node_modules，不能继续沿用上次成功的签名。
    stamp.unlink(missing_ok=True)
    print("安装 Vue 锁定依赖（npm ci）…", flush=True)
    process = start(Service("Vue 依赖安装", [service.command[0], "ci", "--no-audit", "--no-fund"], web), env)
    processes.append(process)
    result = process.wait()
    if result != 0:
        raise RuntimeError(f"Vue 依赖安装失败（npm ci 退出码 {result}），未启动项目服务。")
    stop([process])
    processes.remove(process)
    if not modules.is_dir():
        raise RuntimeError("npm ci 已结束，但 web/node_modules 不存在，请检查 npm 输出。")
    if web_install_signature(web) != signature:
        raise RuntimeError("安装期间 Vue 的依赖文件发生变化，请重新启动以按最新锁文件安装。")
    stamp.write_text(json.dumps(signature, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def start(service: Service, env: dict[str, str]) -> subprocess.Popen:
    if service.config_path:
        service.config_path.parent.mkdir(parents=True, exist_ok=True)
    if service.binary_source:
        service.cwd.mkdir(parents=True, exist_ok=True)
        runtime = Path(service.command[0])
        # goqbot 的运行数据与自更新在可执行文件旁；配置通过 -config 单独指定。
        # 仅首次复制，不覆盖其自更新版本。
        if not runtime.exists():
            shutil.copy2(service.binary_source, runtime)
            if os.name != "nt":
                runtime.chmod(runtime.stat().st_mode | 0o100)
    kwargs = {"creationflags": subprocess.CREATE_NEW_PROCESS_GROUP} if os.name == "nt" else {"start_new_session": True}
    return subprocess.Popen(service.command, cwd=service.cwd, env=env, **kwargs)


def wait_ready(service: Service, process: subprocess.Popen, timeout: float) -> None:
    if not service.health:
        return
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        if process.poll() is not None:
            raise RuntimeError(f"{service.name} 在启动完成前退出（{process.returncode}）。")
        try:
            with LOCAL.open(service.health, timeout=1) as response:
                if service.health_kind == "html":
                    content_type = response.headers.get("Content-Type", "").split(";", 1)[0].strip().lower()
                    if response.status == 200 and content_type == "text/html":
                        return
                else:
                    payload = json.load(response)
                    if (response.status == 200 and isinstance(payload, dict) and payload.get("ok")
                            and payload.get("service") == service.health_service):
                        return
        except (OSError, ValueError):
            pass
        time.sleep(0.2)
    raise RuntimeError(f"等待 {service.name} 启动超时：{service.health}")


def _group_alive(pid: int) -> bool:
    try:
        os.killpg(pid, 0)
        return True
    except ProcessLookupError:
        return False


def stop(processes: list[subprocess.Popen], grace: float = 15) -> None:
    """只清理本次创建的进程组；即使 uv 已退出，也回收同组的服务子进程。"""
    if os.name == "nt":
        for process in reversed(processes):
            if process.poll() is None:
                try:
                    process.send_signal(signal.CTRL_BREAK_EVENT)
                except OSError:
                    pass
        for process in reversed(processes):
            try:
                process.wait(timeout=grace)
            except subprocess.TimeoutExpired:
                subprocess.run(["taskkill", "/PID", str(process.pid), "/T", "/F"], check=False,
                               stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
                process.wait(timeout=5)
        return
    for process in reversed(processes):
        try:
            os.killpg(process.pid, signal.SIGTERM)
        except ProcessLookupError:
            pass
    deadline = time.monotonic() + grace
    while time.monotonic() < deadline:
        for process in processes:
            process.poll()
        if not any(_group_alive(process.pid) for process in processes):
            break
        time.sleep(0.1)
    for process in reversed(processes):
        try:
            os.killpg(process.pid, signal.SIGKILL)
        except ProcessLookupError:
            pass
        process.wait(timeout=5)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--reload", action="store_true", help="后端代码修改后自动重载")
    parser.add_argument("--check", action="store_true", help="只检查目录、命令和端口，不启动服务")
    args = parser.parse_args(argv)
    processes = []
    previous = {sig: signal.getsignal(sig) for sig in (signal.SIGINT, signal.SIGTERM)}

    def interrupted(*_):
        # uv 与外层进程管理器可能重复投递停止信号；清理开始后不可再次打断。
        for sig in previous:
            signal.signal(sig, signal.SIG_IGN)
        raise KeyboardInterrupt

    for sig in previous:
        signal.signal(sig, interrupted)
    try:
        services, skipped = plan(ROOT, reload=args.reload)
        for message in skipped:
            print(message, flush=True)
        env = child_environment(ROOT)
        setup = next((s for s in services if s.config_path and not s.config_path.is_file()), None)
        if setup:
            print(f"goqbot 将在首次启动时生成 {setup.config_path.relative_to(ROOT)}。", flush=True)
            if not args.check:
                print("先由 goqbot 生成配置；填写完成后再次运行 uv run main.py 启动全部服务。", flush=True)
                process = start(setup, env)
                processes.append(process)
                result = process.wait()
                if result == 0 and not setup.config_path.is_file():
                    raise RuntimeError("goqbot 已退出，但未生成配置文件，请检查程序版本和启动参数。")
                return result
        ensure_ports_free(services)
        if args.check:
            for service in services:
                print(f"已检查 {service.name}：{service.cwd.relative_to(ROOT)}")
            return 0
        prepare_web_dependencies(ROOT, services, env, processes)
        timeout = float(configuration(ROOT).get("launcher", {}).get("startup_timeout", 120))
        for service in services:
            print(f"启动 {service.name}…", flush=True)
            process = start(service, env)
            processes.append(process)
            wait_ready(service, process, timeout)
            if any(p.poll() is not None for p in processes):
                raise RuntimeError("有服务在启动期间退出，正在停止本次启动的全部服务。")
        print("所有已配置组件已启动，按 Ctrl+C 停止。", flush=True)
        while all(p.poll() is None for p in processes):
            time.sleep(0.3)
        raise RuntimeError("有服务退出，正在停止本次启动的全部服务。")
    except KeyboardInterrupt:
        print("正在停止本次启动的全部服务…", flush=True)
        return 0
    except (OSError, RuntimeError, ValueError) as exc:
        print(f"启动失败：{exc}", file=sys.stderr, flush=True)
        return 1
    finally:
        for sig in previous:
            signal.signal(sig, signal.SIG_IGN)
        try:
            stop(processes)
        finally:
            for sig, handler in previous.items():
                signal.signal(sig, handler)


if __name__ == "__main__":
    raise SystemExit(main())
