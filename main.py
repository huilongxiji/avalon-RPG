"""在项目根目录运行 uv run main.py，依次启动后端、NoneBot 和已配置的可选组件。"""

from __future__ import annotations

import argparse
import asyncio
import hashlib
import json
import math
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
from typing import Any
from urllib.error import HTTPError, URLError
from urllib.parse import urlsplit

ROOT = Path(__file__).resolve().parent
sys.pycache_prefix = str(ROOT / "data" / "cache" / "python")
os.environ["PYTHONPYCACHEPREFIX"] = sys.pycache_prefix
LOCAL = urllib.request.build_opener(urllib.request.ProxyHandler({}))
if str(ROOT / "servers") not in sys.path:
    sys.path.insert(0, str(ROOT / "servers"))


def output(*args: Any, **kwargs: Any) -> None:
    """SSH 终端已关闭时，日志写入失败不能阻止进程回收。"""
    kwargs.setdefault("flush", True)
    stream = kwargs.get("file") or sys.stdout
    try:
        print(*args, **kwargs)
    except (OSError, ValueError):
        if stream is not sys.stdout and stream is not sys.stderr:
            return
        try:
            descriptor = stream.fileno()
            sink = os.open(os.devnull, os.O_WRONLY)
            try:
                os.dup2(sink, descriptor)
            finally:
                if sink != descriptor:
                    os.close(sink)
        except (OSError, ValueError, AttributeError):
            replacement = open(os.devnull, "w")
            if stream is sys.stdout:
                sys.stdout = replacement
            else:
                sys.stderr = replacement
        # 解释器退出还会 flush 标准流；改接空设备避免清理成功却返回 120。


def stop_signals() -> tuple[signal.Signals, ...]:
    signals = (signal.SIGINT, signal.SIGTERM)
    hangup = getattr(signal, "SIGHUP", None)
    # nohup 明确忽略的 SIGHUP 应继续忽略；前台 SSH 断联则正常清理。
    if hangup is not None and signal.getsignal(hangup) != signal.SIG_IGN:
        signals += (hangup,)
    return signals


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
    key: str = ""
    dependencies: tuple[str, ...] = ()
    checks: tuple[tuple[str, str, str], ...] = ()
    watch_paths: tuple[Path, ...] = ()
    extra_env: tuple[tuple[str, str], ...] = ()


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
                servers, health_url(host, port), "api", key="backend",
                checks=((health_url(host, port), "api", "json"),
                        ("http://127.0.0.1:7901/health", "logic", "json")),
                watch_paths=(servers / "api/src", servers / "logic/src", servers / "contracts/src",
                             servers / "app.py", servers / "pyproject.toml", servers / "uv.lock")),
        Service("NoneBot", [uv, "run", "--locked", "bot.py"], bot,
                health_url(bot_host, bot_port), "bot", key="nonebot", dependencies=("backend",),
                watch_paths=(bot / "src", bot / "bot.py", bot / "pyproject.toml", bot / "uv.lock",
                             servers / "contracts/src"), extra_env=(("FASTAPI_RELOAD", "false"),)),
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
                                health=health_url(bot_host, bot_port) + "/onebot", health_kind="onebot",
                                binary_source=source, config_path=config, key="goqbot", dependencies=("nonebot",)))
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
                                health_kind="html", key="web", dependencies=("backend",)))
    else:
        skipped.append("Vue 尚未迁入或已禁用，本阶段跳过。")
    return services, skipped


def ensure_ports_free(services: list[Service]) -> None:
    # goqbot 的健康入口属于 NoneBot，不能把它当作 goqbot 要绑定的端口。
    urls = [url for service in services if service.key != "goqbot"
            for url, _, _ in (service.checks or ((service.health, "", ""),)) if url]
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
    output("安装 Vue 锁定依赖（npm ci）…")
    process = start_temporary(
        Service("Vue 依赖安装", [service.command[0], "ci", "--no-audit", "--no-fund"], web), env, processes)
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
    if service.key and service.key != "goqbot":
        # 每次恢复也检查端口，避免残留子进程或其他程序占用时启动第二份。
        ensure_ports_free([service])
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
    from launcher.processes import identity

    process = subprocess.Popen(service.command, cwd=service.cwd, env={**env, **dict(service.extra_env)}, **kwargs)
    process._avalon_identity = identity(process.pid)
    return process


def start_temporary(service: Service, env: dict[str, str], processes: list[subprocess.Popen]) -> subprocess.Popen:
    """仅主线程准备阶段使用：完成进程身份与清理登记后再处理停止信号。"""
    previous = {}
    pending = []

    def defer(sig, frame):
        if not pending:
            pending.append((sig, frame))

    for sig in stop_signals():
        handler = signal.getsignal(sig)
        if callable(handler):
            previous[sig] = handler
            signal.signal(sig, defer)
    try:
        process = start(service, env)
        processes.append(process)
        return process
    finally:
        for sig, handler in previous.items():
            signal.signal(sig, handler)
        if pending:
            sig, frame = pending[0]
            previous[sig](sig, frame)


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


def stop(processes: list[subprocess.Popen], grace: float = 10) -> None:
    """按创建时记录的进程身份结束进程树，防止 PID 复用时误伤其他程序。"""
    from launcher.processes import terminate_group

    errors = []
    for process in reversed(processes):
        original = getattr(process, "_avalon_identity", None)
        if original is None:
            if process.poll() is None:
                errors.append("无法确认进程身份，未发送结束信号")
            continue
        try:
            terminate_group(original.pid, original.created, grace=grace)
            process.wait(timeout=2)
        except (OSError, RuntimeError, subprocess.TimeoutExpired) as exc:
            errors.append(str(exc))
    if errors:
        raise RuntimeError("；".join(errors))


ALIASES = {"bot": "nonebot", "servers": "backend", "vue": "web"}
COMPONENTS = {"backend", "nonebot", "goqbot", "web"}
LABELS = {"starting": "启动中", "running": "运行中", "external": "外部运行",
          "unhealthy": "健康异常", "offline": "断线", "stopped": "已停止",
          "stopping": "停止中", "restarting": "恢复中", "waiting": "等待依赖",
          "backoff": "退避等待", "updating": "等待自行重启"}


def targets(values: list[str] | None, *, reload: bool = False) -> list[str]:
    result = list(dict.fromkeys(ALIASES.get(value, value) for value in values or ["all"]))
    allowed = {"backend", "nonebot"} if reload else COMPONENTS
    if "all" in result:
        if len(result) > 1:
            raise ValueError("all 不能和其他组件同时指定")
        return sorted(allowed) if reload else ["all"]
    unknown = set(result) - allowed
    if unknown:
        raise ValueError(f"不支持的组件：{'、'.join(sorted(unknown))}；可用：{'、'.join(sorted(allowed))}")
    return result


def launcher_settings(root: Path, reload_components: list[str] | None = None) -> dict[str, Any]:
    config = configuration(root)
    defaults: dict[str, Any] = {
        "startup_timeout": 120, "health_interval": 10, "health_failures": 3,
        "restart_backoff_initial": 1, "restart_backoff_max": 60, "stable_seconds": 60,
        "shutdown_grace": 10, "poll_interval": 0.25, "reload_debounce": 0.6,
        "goqbot_restart_grace": 120, "goqbot_offline_grace": 300,
    }
    values = config.get("launcher", {})
    settings = {**defaults, **{key: values[key] for key in defaults if key in values}}
    for key in defaults:
        value = settings[key]
        if isinstance(value, bool) or not isinstance(value, (int, float)) or not 0 < value < 86400:
            raise ValueError(f"launcher.{key} 必须是大于 0 且小于 86400 的数值")
    if not isinstance(settings["health_failures"], int):
        raise ValueError("launcher.health_failures 必须是整数")
    if settings["restart_backoff_max"] < settings["restart_backoff_initial"]:
        raise ValueError("restart_backoff_max 不能小于 restart_backoff_initial")
    watched = reload_components if reload_components is not None else values.get("reload", [])
    if not isinstance(watched, list) or not all(isinstance(item, str) for item in watched):
        raise ValueError("launcher.reload 必须是组件名称数组")
    settings["reload_components"] = targets(watched, reload=True) if watched else []
    return settings


def probe(service: Service) -> dict[str, Any]:
    """检查本组件全部健康入口；goqbot 只确认 OneBot 连接，不登录或更新 QQ。"""
    checks = service.checks or ((service.health, service.health_service, service.health_kind),)
    for url, expected, kind in checks:
        if not url:
            continue
        try:
            with LOCAL.open(url, timeout=1) as response:
                if kind == "html":
                    if response.status != 200 or response.headers.get_content_type() != "text/html":
                        return {"ok": False, "reason": "网站未返回正常页面"}
                    continue
                body = json.loads(response.read(65536))
                if not isinstance(body, dict):
                    return {"ok": False, "reason": "健康响应格式不正确"}
                if kind == "onebot":
                    connected = body.get("connected")
                    if type(connected) is not int or connected <= 0:
                        return {"ok": False, "reason": "尚无 OneBot 连接"}
                elif body.get("ok") is not True or body.get("service") != expected:
                    return {"ok": False, "reason": f"{expected} 健康检查未通过"}
        except HTTPError as exc:
            detail = f"HTTP {exc.code}"
        except URLError as exc:
            if isinstance(exc.reason, ConnectionRefusedError):
                detail = "连接被拒绝，服务尚未监听"
            elif isinstance(exc.reason, TimeoutError):
                detail = "连接超时"
            else:
                detail = type(exc.reason).__name__
        except (OSError, ValueError) as exc:
            detail = type(exc).__name__
        else:
            continue
        address = urlsplit(url)
        target = f"{expected or service.key or service.name} {address.hostname}:{address.port}"
        return {"ok": False, "reason": f"{target} 健康检查失败：{detail}"}
    return {"ok": True, "reason": "健康检查通过"}


async def run_managed(root: Path, services: list[Service], env: dict[str, str], settings: dict) -> int:
    from launcher.control import ControlServer
    from launcher.processes import find_goqbot, terminate
    from launcher.supervisor import Supervisor
    from launcher.watch import SourceWatcher

    watcher = SourceWatcher(debounce=settings["reload_debounce"])
    supervisor = Supervisor(
        root, services, env, settings, start_fn=start,
        stop_fn=lambda processes: stop(processes, grace=settings["shutdown_grace"]),
        probe_fn=probe,
        scan_fn=lambda service: find_goqbot(Path(service.command[0]), service.config_path),
        stop_matches_fn=lambda matches: terminate(matches, grace=settings["shutdown_grace"]),
        watcher_fn=watcher.changed,
        echo=output,
    )
    loop = asyncio.get_running_loop()

    def handle(payload: dict) -> dict:
        options = {"enabled": payload["enabled"]} if "enabled" in payload else {}
        future = asyncio.run_coroutine_threadsafe(
            supervisor.command(payload["action"], payload.get("targets"), options), loop)
        return future.result(timeout=30)

    server = ControlServer(root, handle).start()
    previous = {sig: signal.getsignal(sig) for sig in stop_signals()}
    for sig in previous:
        try:
            loop.add_signal_handler(sig, supervisor.request_shutdown)
        except (NotImplementedError, RuntimeError):
            signal.signal(sig, lambda *_: loop.call_soon_threadsafe(supervisor.request_shutdown))
    shutdown_error = None
    try:
        output("运行监护已启用；另开终端用 uv run main.py status 查看，Ctrl+C 停止本次管理的服务。")
        await supervisor.run()
        return 0
    except BaseException as exc:
        shutdown_error = str(exc) or type(exc).__name__
        raise
    finally:
        try:
            await asyncio.to_thread(server.close, error=shutdown_error)
        finally:
            for sig, handler in previous.items():
                try:
                    loop.remove_signal_handler(sig)
                except (NotImplementedError, RuntimeError):
                    pass
                signal.signal(sig, handler)


def parser() -> argparse.ArgumentParser:
    result = argparse.ArgumentParser(description="统一启动、持续监护与运行中组件管理")
    result.add_argument("--check", action="store_true", help="只读检查，不启动、不创建运行文件")
    result.add_argument("--reload", nargs="*", metavar="组件", help="监听组件源码；不填组件时为 backend")
    sub = result.add_subparsers(dest="action")
    for action, help_text in (("status", "查询运行中组件"), ("start", "启动已停止的组件及其依赖"),
                              ("stop", "停止指定组件并保持停止"), ("restart", "重启指定组件")):
        command = sub.add_parser(action, help=help_text)
        command.add_argument("targets", nargs="*", metavar="组件", help="backend / nonebot / goqbot / web / all")
        if action == "status":
            command.add_argument("--json", action="store_true", help="输出机器可读状态")
    reload_command = sub.add_parser("reload", help="切换 backend / nonebot 的源码自动重载")
    reload_command.add_argument("targets", nargs="+", metavar="组件")
    reload_command.add_argument("--off", action="store_true", help="关闭源码监听")
    down_command = sub.add_parser("down", help="关闭监护及本次管理的组件，并等待退出结果")
    down_command.add_argument("--timeout", type=float, default=90, metavar="秒", help="等待关闭的秒数，默认 90")
    sub.add_parser("check", help="与 --check 相同")
    return result


def print_states(result: dict) -> None:
    rows = result.get("states", result.get("services", []))
    output(f"{'组件':<12}{'状态':<10}{'进程':<9}{'重启':<7}{'源码监听':<10}说明")
    for item in rows:
        status = LABELS.get(item.get("status", ""), item.get("status", "未知"))
        output(f"{item.get('key', ''):<12}{status:<10}{str(item.get('pid') or '—'):<9}"
              f"{str(item.get('restarts', 0)):<7}{'开' if item.get('reload') else '关':<10}{item.get('message', '')}")


def main(argv: list[str] | None = None) -> int:
    args = parser().parse_args(argv)
    from launcher.control import ControlError, InstanceLock, request, wait_stopped

    try:
        if args.action not in (None, "check"):
            if args.check or args.reload is not None:
                raise ValueError("运行中管理命令请不要同时使用启动选项 --check/--reload")
            action = args.action
            selected = targets(getattr(args, "targets", None), reload=action == "reload")
            payload: dict[str, Any] = {"action": action, "targets": selected}
            if action == "reload":
                payload["enabled"] = not args.off
            if action == "down" and (not math.isfinite(args.timeout) or not 0 < args.timeout < 86400):
                raise ValueError("down --timeout 必须大于 0 且小于 86400 秒")
            result = request(ROOT, payload, timeout=35)
            if action == "down" and result.get("ok", True):
                output("关闭请求已受理，正在等待组件清理和启动器退出…")
                result = wait_stopped(ROOT, result["instance_id"], timeout=args.timeout)
                if result.get("ok"):
                    output(result["message"])
                    return 0
                output(result.get("error") or "无法确认关闭结果。", file=sys.stderr)
                return 1
            if getattr(args, "json", False):
                output(json.dumps(result, ensure_ascii=False, indent=2))
            else:
                if not result.get("ok", True):
                    output(result.get("error") or result.get("message") or "管理请求失败。", file=sys.stderr)
                elif action != "status":
                    output(result.get("message") or "管理请求已受理，组件状态将按请求更新。")
                print_states(result)
            return 0 if result.get("ok", True) else 1

        reload_components = (["backend"] if args.reload == [] else targets(args.reload, reload=True)) if args.reload is not None else None
        settings = launcher_settings(ROOT, reload_components)
        services, skipped = plan(ROOT)
        for message in skipped:
            output(message)
        if args.check or args.action == "check":
            ensure_ports_free(services)
            for service in services:
                output(f"已检查 {service.key or service.name}：{service.cwd.relative_to(ROOT)}")
                if service.config_path and not service.config_path.is_file():
                    output(f"首次启动时生成 {service.config_path.relative_to(ROOT)}")
            return 0
        with InstanceLock(ROOT):
            env = child_environment(ROOT)
            # 原生程序负责首次生成配置；此路径不安装网站依赖，也不要求业务端口空闲。
            setup = next((s for s in services if s.config_path and not s.config_path.is_file()), None)
            temporary: list[subprocess.Popen] = []
            previous = {sig: signal.getsignal(sig) for sig in stop_signals()}

            def interrupted(*_):
                for sig in previous:
                    signal.signal(sig, signal.SIG_IGN)
                raise KeyboardInterrupt

            for sig in previous:
                signal.signal(sig, interrupted)
            try:
                if setup:
                    output(f"goqbot 将生成 {setup.config_path.relative_to(ROOT)}；填写后重新启动项目。")
                    process = start_temporary(setup, env, temporary)
                    result = process.wait()
                    if result == 0 and not setup.config_path.is_file():
                        raise RuntimeError("goqbot 已退出但未生成配置，请检查其版本与参数。")
                    return result
                ensure_ports_free(services)
                prepare_web_dependencies(ROOT, services, env, temporary)
                return asyncio.run(run_managed(ROOT, services, env, settings))
            finally:
                for sig in previous:
                    signal.signal(sig, signal.SIG_IGN)
                try:
                    stop(temporary)
                finally:
                    for sig, handler in previous.items():
                        signal.signal(sig, handler)
    except KeyboardInterrupt:
        output("已停止本次启动。")
        return 0
    except (OSError, RuntimeError, ValueError, ControlError) as exc:
        output(f"运行管理失败：{exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
