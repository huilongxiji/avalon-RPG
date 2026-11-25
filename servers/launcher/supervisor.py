"""Component supervision without importing the root command-line entry point.

All process operations are injected, so the state machine can be tested without
starting a game server. The local control server owns transport and authentication.
"""

from __future__ import annotations

import asyncio
import inspect
import time
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable


@dataclass
class Managed:
    service: Any
    desired: bool = True
    process: Any = None
    original_identity: Any = None
    current_identity: Any = None
    owned: bool = False
    status: str = "starting"
    reason: str = "等待启动"
    last_ok: str | None = None
    starts: int = 0
    restarts: int = 0
    failures: int = 0
    started_at: float = 0.0
    healthy_since: float | None = None
    next_probe: float = 0.0
    next_start: float = 0.0
    backoff: float = 1.0
    ever_ready: bool = False
    ever_seen: bool = False
    lost_since: float | None = None
    offline_since: float | None = None
    restart_requested: bool = False
    stop_requested: bool = False
    reload_enabled: bool = False
    stop_guard: bool = False
    stop_warning: str = ""
    goq_retry_scheduled: bool = False
    generation: int = 0
    lock: asyncio.Lock = field(default_factory=asyncio.Lock)
    wake: asyncio.Event = field(default_factory=asyncio.Event)


class Supervisor:
    """Manage a single launcher's desired state and its owned process trees."""

    def __init__(
        self, root: Path, services: list[Any], env: dict[str, str], settings: dict[str, Any],
        *, start_fn: Callable, stop_fn: Callable, probe_fn: Callable,
        scan_fn: Callable | None = None, stop_matches_fn: Callable | None = None,
        watcher_fn: Callable | None = None, identity_fn: Callable | None = None,
        refresh_group_fn: Callable | None = None, clock: Callable[[], float] = time.monotonic,
        echo: Callable[[str], None] = print,
    ) -> None:
        self.root, self.env, self.settings = Path(root), env, settings
        self.start_fn, self.stop_fn, self.probe_fn = start_fn, stop_fn, probe_fn
        self.scan_fn, self.stop_matches_fn, self.watcher_fn = scan_fn, stop_matches_fn, watcher_fn
        if identity_fn is None or refresh_group_fn is None:
            from . import processes
            identity_fn = identity_fn or processes.identity
            refresh_group_fn = refresh_group_fn or processes.refresh_group
        self.identity_fn, self.refresh_group_fn = identity_fn, refresh_group_fn
        self.clock = clock
        self.echo = echo
        self.output_error: str | None = None
        self._observed: dict[str, tuple[Any, ...]] = {}
        self.started = asyncio.Event()
        self.stopping = asyncio.Event()
        self.running = False
        self.items: dict[str, Managed] = {}
        initial = self._number("restart_backoff_initial", 1.0, minimum=0.01)
        reload_components = set(settings.get("reload_components", []))
        for service in services:
            key = service.key
            if key in self.items:
                raise ValueError(f"重复组件：{key}")
            self.items[key] = Managed(service, backoff=initial,
                                      reload_enabled=key in reload_components and key in {"backend", "nonebot"})
        self.order = self._dependency_order()

    def _number(self, name: str, default: float, *, minimum: float = 0.0) -> float:
        return max(minimum, float(self.settings.get(name, default)))

    def _dependency_order(self) -> list[str]:
        result: list[str] = []
        visiting: set[str] = set()

        def visit(key: str) -> None:
            if key in result:
                return
            if key in visiting:
                raise ValueError(f"组件依赖形成循环：{key}")
            if key not in self.items:
                raise ValueError(f"缺少依赖组件：{key}")
            visiting.add(key)
            for dependency in self.items[key].service.dependencies:
                visit(dependency)
            visiting.remove(key)
            result.append(key)

        for key in self.items:
            visit(key)
        return result

    @staticmethod
    async def _call(function: Callable, *args: Any) -> Any:
        if inspect.iscoroutinefunction(function):
            return await function(*args)
        result = await asyncio.to_thread(function, *args)
        return await result if inspect.isawaitable(result) else result

    def states(self, keys: list[str] | None = None) -> list[dict[str, Any]]:
        result = []
        for key in self.order:
            if keys is not None and key not in keys:
                continue
            item = self.items[key]
            pid = getattr(item.current_identity, "pid", None)
            if pid is None and item.process is not None and item.process.poll() is None:
                pid = item.process.pid
            result.append({
                "key": key, "name": item.service.name, "status": item.status,
                "pid": pid, "restarts": item.restarts, "counter": item.restarts,
                "last_ok": item.last_ok, "message": item.reason, "reason": item.reason,
                "desired": "running" if item.desired else "stopped", "owned": item.owned,
                "reload": item.reload_enabled, "failures": item.failures,
            })
        return result

    def request_shutdown(self) -> None:
        self.stopping.set()
        for item in self.items.values():
            item.wake.set()

    async def command(self, action: str, targets: list[str] | None = None,
                      options: dict[str, Any] | None = None) -> dict[str, Any]:
        options = options or {}
        keys = list(self.order) if not targets or "all" in targets else list(dict.fromkeys(targets))
        unknown = [key for key in (targets or []) if key != "all" and key not in self.items]
        if unknown:
            return {"ok": False, "error": "未配置组件：" + ", ".join(unknown), "states": self.states()}
        if action == "status":
            return {"ok": True, "states": self.states(keys)}
        if action == "down":
            # Give the authenticated IPC worker time to send its acknowledgement.
            asyncio.get_running_loop().call_later(0.2, self.request_shutdown)
            return {"ok": True, "accepted": True, "states": self.states()}
        if action not in {"start", "stop", "restart", "reload"}:
            return {"ok": False, "error": f"未知操作：{action}", "states": self.states()}
        if self.stopping.is_set():
            return {"ok": False, "error": "启动器正在退出", "states": self.states()}
        if action == "reload":
            unsupported = [key for key in keys if key not in {"backend", "nonebot"}]
            if unsupported:
                return {"ok": False, "error": "仅 backend、nonebot 支持代码监听；goqbot 自行管理，web 使用 Vite HMR",
                        "states": self.states()}
            for key in keys:
                item = self.items[key]
                item.reload_enabled = bool(options.get("enabled", True))
                item.generation += 1
                item.wake.set()
            return {"ok": True, "accepted": True, "states": self.states()}

        def enable(key: str, *, dependencies: bool = True) -> None:
            item = self.items[key]
            if dependencies:
                for dependency in item.service.dependencies:
                    enable(dependency)
            if not item.desired and key == "goqbot":
                item.ever_seen = False
                item.goq_retry_scheduled = False
            item.desired = True
            item.stop_requested = False
            item.stop_guard = False
            item.stop_warning = ""
            item.next_start = 0.0
            item.generation += 1
            item.wake.set()

        for key in keys:
            item = self.items[key]
            if action == "start":
                enable(key)
            elif action == "stop":
                item.desired = False
                item.stop_requested = True
                item.stop_guard = key == "goqbot"
                item.restart_requested = False
                item.generation += 1
                item.wake.set()
            else:
                # Only start recursively enables dependencies; restart preserves
                # the operator's separate stop intent on all other components.
                enable(key, dependencies=False)
                item.restart_requested = True
                item.reason = "已请求重启"
        return {"ok": True, "accepted": True, "states": self.states()}

    async def run(self) -> None:
        if self.running:
            raise RuntimeError("Supervisor 已经运行")
        self.running = True
        tasks = [asyncio.create_task(self._worker(key), name=f"supervise-{key}") for key in self.order]
        self.started.set()
        try:
            await self.stopping.wait()
        finally:
            self.request_shutdown()
            await asyncio.gather(*tasks, return_exceptions=True)
            cleanup_errors = []
            # Leave any initially attached external goqbot process alone.
            for key in reversed(self.order):
                item = self.items[key]
                async with item.lock:
                    if item.owned:
                        try:
                            await self._stop(item, explicit=False)
                        except Exception as exc:  # keep cleaning the other owned components
                            item.status, item.reason = "unhealthy", f"停止失败：{exc}"
                            cleanup_errors.append(f"{key}：{exc}")
                        self._announce(key)
            self.running = False
            if cleanup_errors:
                raise RuntimeError("部分组件未能确认停止；" + "；".join(cleanup_errors))

    async def _worker(self, key: str) -> None:
        item = self.items[key]
        while not self.stopping.is_set():
            item.wake.clear()
            try:
                await self.tick(key)
            except Exception as exc:
                item.status, item.reason = "unhealthy", f"监督检查失败：{exc}"
            self._announce(key)
            if self.stopping.is_set():
                break
            try:
                await asyncio.wait_for(item.wake.wait(), self._number("poll_interval", 0.5, minimum=0.01))
            except TimeoutError:
                pass

    def _announce(self, key: str) -> None:
        state = self.states([key])[0]
        current = tuple(state[name] for name in ("status", "reason", "pid", "desired", "reload"))
        if self._observed.get(key) == current:
            return
        self._observed[key] = current
        labels = {"starting": "等待就绪", "running": "运行中", "external": "附着已有进程",
                  "stopped": "已停止", "restarting": "等待重启", "unhealthy": "需要检查", "offline": "连接离线"}
        pid = f"（PID {state['pid']}）" if state['pid'] is not None else ""
        try:
            self.echo(f"[{state['name']}] {labels.get(state['status'], state['status'])}{pid}：{state['reason']}")
        except (OSError, ValueError) as exc:
            # SSH/terminal loss can close the fd (OSError) or TextIO stream
            # (ValueError). Logging must not stop a worker or skip cleanup.
            # Do not fall back to stderr: it may be the same closed terminal.
            self.output_error = f"{type(exc).__name__}: {exc}"
        else:
            self.output_error = None

    async def tick(self, key: str) -> None:
        """One deterministic supervision step; public for isolated state tests."""
        item = self.items[key]
        async with item.lock:
            if self.stopping.is_set():
                return
            if item.original_identity is not None:
                await self._call(self.refresh_group_fn, item.original_identity)
            if not item.desired:
                if item.process is not None or item.current_identity is not None or item.stop_requested or item.stop_guard:
                    explicit = item.stop_requested or item.stop_guard
                    generation = item.generation
                    await self._stop(item, explicit=explicit)
                    if generation == item.generation:
                        item.stop_requested = False
                if item.stop_warning:
                    item.status, item.reason = "unhealthy", item.stop_warning
                else:
                    item.status, item.reason = "stopped", "已手动停止；不会自动启动"
                return
            if item.restart_requested:
                item.restart_requested = False
                generation = item.generation
                try:
                    await self._stop(item, explicit=True)
                except Exception:
                    if generation == item.generation:
                        item.restart_requested = True
                    raise
                item.next_start = 0.0
                if key == "goqbot":
                    item.ever_seen = False
                    item.goq_retry_scheduled = False
                if not item.desired or self.stopping.is_set():
                    return
            if item.reload_enabled and self.watcher_fn and key in {"backend", "nonebot"}:
                generation = item.generation
                changed = await self._call(self.watcher_fn, item.service)
                if (generation != item.generation or not item.reload_enabled
                        or not item.desired or self.stopping.is_set()):
                    return
                if changed:
                    try:
                        await self._stop(item, explicit=True)
                    except Exception:
                        item.restart_requested = True
                        raise
                    item.next_start = 0.0
                    item.reason = "代码已变更，正在重载当前组件"
                    if not item.desired or self.stopping.is_set():
                        return
            if key == "goqbot":
                await self._goqbot(item)
            else:
                await self._normal(item)

    def _dependencies(self, item: Managed) -> list[str]:
        return [key for key in item.service.dependencies
                if not self.items[key].desired or self.items[key].status not in {"running", "external"}]

    def _waiting(self, item: Managed, dependencies: list[str]) -> None:
        item.status = "starting"
        item.reason = "等待依赖就绪：" + ", ".join(dependencies)
        item.failures = 0
        item.healthy_since = None
        item.offline_since = None

    async def _spawn(self, item: Managed) -> None:
        if not item.desired or self.stopping.is_set():
            return
        try:
            process = await self._call(self.start_fn, item.service, self.env)
        except Exception as exc:
            self._retry(item, f"启动失败：{exc}")
            return
        item.process = process
        item.owned = True
        item.original_identity = getattr(process, "_avalon_identity", None)
        if item.original_identity is None:
            item.original_identity = await self._call(self.identity_fn, process.pid)
        item.current_identity = item.original_identity
        item.starts += 1
        item.restarts = max(0, item.starts - 1)
        item.started_at = self.clock()
        item.next_probe = 0.0
        item.failures = 0
        item.ever_ready = False
        item.healthy_since = None
        item.lost_since = None
        item.offline_since = None
        item.stop_warning = ""
        item.goq_retry_scheduled = False
        item.ever_seen = True
        item.status, item.reason = "starting", "进程已启动，等待就绪"

    async def _stop(self, item: Managed, *, explicit: bool) -> None:
        identities: list[Any] = []
        warning = ""
        was_owned = item.owned
        uncertain_ownership = False
        known = {(identity.pid, identity.created) for identity in
                 (item.current_identity, item.original_identity) if identity is not None}
        if item.service.key == "goqbot":
            if explicit or was_owned:
                if self.scan_fn is None:
                    raise RuntimeError("缺少精确进程扫描器，无法确认 goqbot 已停止")
                scan = await self._call(self.scan_fn, item.service)
                if explicit or (not scan.uncertain and len(scan.processes) == 1):
                    identities.extend(scan.processes)
                elif item.current_identity is not None:
                    identities.append(item.current_identity)
                if scan.uncertain:
                    warning = scan.message or "仍有无法核实的 goqbot 进程，不能确认已完全停止"
                elif len(scan.processes) > 1 and not explicit:
                    warning = "存在多个 goqbot 匹配，不能确认其余进程归本次启动所有"
                uncertain_ownership = not explicit and (scan.uncertain or len(scan.processes) > 1)
            if identities:
                if self.stop_matches_fn is None:
                    raise RuntimeError("缺少精确进程停止器，无法停止 goqbot")
                # Exact process identities only; never match by name or port.
                unique = {(identity.pid, identity.created): identity for identity in identities}
                await self._call(self.stop_matches_fn, list(unique.values()))
        if item.process is not None:
            await self._call(self.stop_fn, [item.process])
        if item.service.key == "goqbot" and (explicit or was_owned):
            # A self-update may detach its successor between the last monitor
            # scan and termination. Recheck after the original tree is gone.
            for attempt in range(4):
                scan = await self._call(self.scan_fn, item.service)
                if scan.uncertain:
                    warning = scan.message or "停止后仍无法核实 goqbot 进程状态"
                    break
                if not scan.processes:
                    warning = ""
                    break
                if not explicit and len(scan.processes) > 1:
                    warning = "停止后存在多个 goqbot 匹配，未猜测结束其余进程"
                    break
                if uncertain_ownership and any((value.pid, value.created) not in known for value in scan.processes):
                    warning = "停止后仍有无法确认归属的 goqbot 进程，未猜测结束"
                    break
                if attempt == 3:
                    warning = "goqbot 停止后仍持续产生接替进程，未能确认完全停止"
                    break
                if self.stop_matches_fn is None:
                    raise RuntimeError("缺少精确进程停止器，无法停止 goqbot")
                await self._call(self.stop_matches_fn, scan.processes)
            if warning and was_owned and not explicit:
                raise RuntimeError(warning)
        item.process = None
        item.original_identity = None
        item.current_identity = None
        item.owned = False
        item.failures = 0
        item.healthy_since = None
        item.lost_since = None
        item.offline_since = None
        item.stop_warning = warning
        item.status, item.reason = ("unhealthy", warning) if warning else ("stopped", "进程已停止")

    def _retry(self, item: Managed, reason: str) -> None:
        delay = item.backoff
        item.next_start = self.clock() + delay
        item.backoff = min(delay * 2, self._number("restart_backoff_max", 60, minimum=delay))
        item.healthy_since = None
        item.failures = 0
        item.status = "restarting"
        item.reason = f"{reason}；{delay:g} 秒后重试"

    def _healthy(self, item: Managed, reason: str) -> None:
        now = self.clock()
        if item.healthy_since is None:
            item.healthy_since = now
        if now - item.healthy_since >= self._number("stable_seconds", 60):
            item.backoff = self._number("restart_backoff_initial", 1, minimum=0.01)
        item.failures = 0
        item.ever_ready = True
        item.last_ok = datetime.now(timezone.utc).isoformat()
        item.status = "external" if not item.owned else "running"
        item.reason = reason or "健康检查通过"

    async def _probe(self, item: Managed) -> tuple[bool, str]:
        try:
            result = await self._call(self.probe_fn, item.service)
        except Exception as exc:
            return False, f"健康检查失败：{exc}"
        if isinstance(result, dict):
            return bool(result.get("ok")), str(result.get("reason") or result.get("message") or "")
        return bool(result), "健康检查通过" if result else "健康检查未通过"

    async def _normal(self, item: Managed) -> None:
        now = self.clock()
        if item.process is not None and item.process.poll() is not None:
            code = item.process.returncode
            await self._stop(item, explicit=False)
            self._retry(item, f"进程退出（{code}）")
        dependencies = self._dependencies(item)
        if dependencies:
            self._waiting(item, dependencies)
            return
        if item.process is None:
            if now >= item.next_start:
                await self._spawn(item)
            return
        if now < item.next_probe:
            return
        generation = item.generation
        item.next_probe = now + self._number("health_interval", 10, minimum=0.01)
        ok, reason = await self._probe(item)
        if generation != item.generation or not item.desired or self.stopping.is_set():
            return
        dependencies = self._dependencies(item)
        if dependencies:
            self._waiting(item, dependencies)
            return
        if ok:
            self._healthy(item, reason)
            return
        item.healthy_since = None
        if not item.ever_ready and now - item.started_at < self._number("startup_timeout", 120):
            item.status, item.reason = "starting", reason or "等待健康接口就绪"
            return
        item.failures += 1
        item.status, item.reason = "unhealthy", reason or "健康检查未通过"
        if item.failures >= int(self._number("health_failures", 3, minimum=1)):
            await self._stop(item, explicit=False)
            self._retry(item, "连续健康检查失败")

    async def _goqbot(self, item: Managed) -> None:
        if self.scan_fn is None:
            item.status, item.reason = "unhealthy", "缺少精确进程扫描器；不会猜测启动 goqbot"
            return
        dependencies = self._dependencies(item)
        if dependencies:
            item.offline_since = None
            item.healthy_since = None
        scan = await self._call(self.scan_fn, item.service)
        if scan.uncertain or len(scan.processes) > 1:
            item.healthy_since = None
            item.status = "unhealthy"
            item.reason = scan.message or "进程状态不确定或存在多个匹配；不会重复启动"
            return
        now = self.clock()
        dependencies = self._dependencies(item)
        if not scan.processes:
            item.healthy_since = None
            # Even a scanner's empty result cannot override our own live child.
            if item.process is not None and item.process.poll() is None:
                item.status, item.reason = "starting", "本次启动的 goqbot 仍在运行，等待精确进程识别"
                return
            item.current_identity = None
            if item.ever_seen and not item.goq_retry_scheduled:
                if item.lost_since is None:
                    item.lost_since = now
                elapsed = now - item.lost_since
                if elapsed < self._number("goqbot_restart_grace", 120):
                    item.status, item.reason = "restarting", "等待 goqbot 自行更新或重启接替，不重复启动"
                    return
                self._retry(item, "goqbot 自行重启宽限已结束，精确扫描确认进程不存在")
                item.goq_retry_scheduled = True
                return
            if dependencies:
                self._waiting(item, dependencies)
                return
            if now < item.next_start:
                return
            if item.process is not None:
                # Reap the original group only after a confident empty scan and
                # the self-restart grace. It may contain the successor meanwhile.
                await self._call(self.stop_fn, [item.process])
                item.process = None
                item.original_identity = None
                # A successor can appear while the original group is reaped.
                # Adopt it instead of terminating it as part of recovery.
                latest = await self._call(self.scan_fn, item.service)
                if latest.uncertain or len(latest.processes) > 1:
                    item.status, item.reason = "unhealthy", latest.message or "清理后进程归属不确定，取消重复启动"
                    return
                if latest.processes:
                    item.current_identity = latest.processes[0]
                    item.lost_since = None
                    item.goq_retry_scheduled = False
                    item.next_probe = 0.0
                    item.status, item.reason = "starting", "已发现 goqbot 自行重启接替，取消重复启动"
                    return
            await self._spawn(item)
            return

        identity = scan.processes[0]
        if item.current_identity != identity:
            item.next_probe = 0.0
            item.healthy_since = None
        item.current_identity = identity
        item.ever_seen = True
        item.lost_since = None
        item.goq_retry_scheduled = False
        item.next_start = 0.0
        if dependencies:
            self._waiting(item, dependencies)
            return
        if now < item.next_probe:
            return
        generation = item.generation
        item.next_probe = now + self._number("health_interval", 10, minimum=0.01)
        ok, reason = await self._probe(item)
        if generation != item.generation or not item.desired or self.stopping.is_set():
            return
        dependencies = self._dependencies(item)
        if dependencies:
            self._waiting(item, dependencies)
            return
        if ok:
            item.offline_since = None
            self._healthy(item, reason)
            return
        item.healthy_since = None
        if item.offline_since is None:
            item.offline_since = now
        if now - item.offline_since < self._number("goqbot_offline_grace", 300):
            item.status, item.reason = "starting", reason or "OneBot 暂时断线，等待自行恢复"
        else:
            item.status, item.reason = "offline", reason or "OneBot 断线超过宽限，请检查登录与连接"
