"""按进程身份管理本项目进程，不用命令行子串或未验证的进程组广播。

创建时间用于防止 PID 复用。POSIX 会话成员需在父进程存活时通过
refresh_group 记录；父进程退出后，仍存活的已记录成员作为组身份锚点。
"""

from __future__ import annotations

import os
import signal
import threading
import time
from dataclasses import dataclass, field
from pathlib import Path

import psutil


@dataclass(frozen=True)
class ProcessIdentity:
    pid: int
    created: float


@dataclass
class ScanResult:
    processes: list[ProcessIdentity]
    uncertain: bool = False
    message: str = ""


class ProcessControlError(RuntimeError):
    """无法安全确认或结束进程；调用者应显示错误而非宣称已停止。"""


@dataclass
class _Group:
    pgid: int
    sid: int
    members: set[ProcessIdentity] = field(default_factory=set)


_groups: dict[ProcessIdentity, _Group] = {}
_lock = threading.RLock()
_GONE = (psutil.NoSuchProcess, psutil.ZombieProcess, ProcessLookupError)
_DENIED = (psutil.AccessDenied, PermissionError)


def _processes():
    # process_iter 缓存 Process 对象；同一个 PID 被复用后不能沿用旧 exe/创建时间。
    for cached in psutil.process_iter():
        try:
            yield psutil.Process(cached.pid)
        except _GONE:
            continue


def _same_user(process: psutil.Process) -> bool:
    if os.name == "posix":
        return process.uids().real == os.getuid()
    return process.username().casefold() == psutil.Process().username().casefold()


def _verified(value: ProcessIdentity) -> psutil.Process | None:
    try:
        process = psutil.Process(value.pid)
        if process.create_time() != value.created or not process.is_running():
            return None
        if process.status() == psutil.STATUS_ZOMBIE:
            return None
        if not _same_user(process):
            return None
        return process
    except _GONE:
        return None


def identity(pid: int) -> ProcessIdentity | None:
    if pid <= 0:
        return None
    try:
        process = psutil.Process(pid)
        value = ProcessIdentity(pid, process.create_time())
        if _verified(value) is None:
            return None
        if os.name == "posix" and os.getpgid(pid) == pid and os.getsid(pid) == pid:
            with _lock:
                _groups.setdefault(value, _Group(pid, pid, {value}))
            refresh_group(value)
        return value
    except (*_GONE, *_DENIED, OSError):
        return None


def alive(value: ProcessIdentity) -> bool:
    try:
        return _verified(value) is not None
    except (*_DENIED, OSError):
        return False


def _path(value: str, cwd: str | None) -> str | None:
    path = Path(value)
    if not path.is_absolute():
        if cwd is None:
            return None
        path = Path(cwd) / path
    return os.path.normcase(str(path.resolve(strict=False)))


def _config_argument(arguments: list[str]) -> tuple[str | None, bool]:
    """多个配置开关不猜优先级；第二项表示配置语法有歧义。"""
    values: list[str] = []
    malformed = False
    for index, arg in enumerate(arguments):
        if arg in {"-config", "--config"}:
            if index + 1 == len(arguments) or arguments[index + 1].startswith("-"):
                malformed = True
            else:
                values.append(arguments[index + 1])
        elif arg.startswith(("-config=", "--config=")):
            value = arg.split("=", 1)[1]
            if value:
                values.append(value)
            else:
                malformed = True
    return (values[0] if len(values) == 1 else None), malformed or len(values) > 1


def find_goqbot(executable: Path, config: Path) -> ScanResult:
    """只匹配当前用户的精确程序和精确 -config 参数，不读取配置内容。

    argv[1] 允许 Python/脚本解释器运行临时测试程序。无法读取潜在候选的
    必要信息时返回 uncertain，调用者不能因此假定没有实例而再启动一个。
    """
    wanted_exe, wanted_config = _path(str(executable), str(Path.cwd())), _path(str(config), str(Path.cwd()))
    matches: set[ProcessIdentity] = set()
    uncertain = False
    missing_config = False
    try:
        for process in _processes():
            try:
                if not _same_user(process):
                    continue
                if process.status() == psutil.STATUS_ZOMBIE:
                    continue
                created = process.create_time()
                try:
                    executable_path = process.exe()
                except _DENIED:
                    executable_path = None
                try:
                    arguments = process.cmdline()
                except _DENIED:
                    # 路径已经明确不同且不存在脚本参数仍不能排除解释器候选。
                    uncertain = True
                    continue
                if not arguments:
                    uncertain = True
                    continue
                paths = ([executable_path] if executable_path else []) + [
                    arg for arg in arguments[:2] if arg and not arg.startswith("-")
                ]
                config_arg, ambiguous = _config_argument(arguments)
                # 绝对程序路径不需要读取 cwd；相对 argv 和相对配置需要它。
                cwd = None
                if any(not Path(path).is_absolute() for path in paths) or (
                    config_arg is not None and not Path(config_arg).is_absolute()
                ):
                    try:
                        cwd = process.cwd()
                    except _DENIED:
                        # 已知的绝对路径不匹配时，相对参数仍可能是目标程序。
                        uncertain = True
                        continue
                if wanted_exe not in {_path(path, cwd) for path in paths}:
                    uncertain = uncertain or executable_path is None
                    continue
                if ambiguous:
                    uncertain = True
                    continue
                if config_arg is None:
                    uncertain = missing_config = True
                    continue
                if _path(config_arg, cwd) != wanted_config:
                    continue
                value = ProcessIdentity(process.pid, created)
                if _verified(value) is not None:
                    matches.add(value)
            except _GONE:
                continue
            except (*_DENIED, OSError, ValueError):
                uncertain = True
    except (*_DENIED, OSError):
        uncertain = True
    message = "部分进程信息无法读取或配置参数有歧义，不能确认是否存在其他实例" if uncertain else ""
    if missing_config:
        message = "发现程序路径匹配但缺少 -config 参数的进程，无法确认配置归属；不会重复启动"
    return ScanResult(sorted(matches, key=lambda item: item.pid), uncertain, message)


def _capture_descendants(value: ProcessIdentity) -> set[ProcessIdentity]:
    process = _verified(value)
    if process is None:
        return set()
    result = {value}
    try:
        children = process.children(recursive=True)
    except _GONE:
        return set()
    for child in children:
        try:
            candidate = ProcessIdentity(child.pid, child.create_time())
            if _verified(candidate) is not None:
                result.add(candidate)
        except _GONE:
            continue
    return result


def _session_matches(value: ProcessIdentity, group: _Group) -> bool:
    try:
        return _verified(value) is not None and os.getpgid(value.pid) == group.pgid and os.getsid(value.pid) == group.sid
    except (*_GONE, *_DENIED):
        return False


def refresh_group(value: ProcessIdentity) -> None:
    """父进程存活期间定期调用，记住其组成员和后代，便于退出后安全回收。"""
    if os.name != "posix":
        # Windows 没有 POSIX 会话，保留可验证的进程树身份即可。
        try:
            descendants = _capture_descendants(value)
        except (*_GONE, *_DENIED, OSError):
            return
        with _lock:
            group = _groups.setdefault(value, _Group(value.pid, value.pid, {value}))
            group.members.update(descendants)
        return
    with _lock:
        group = _groups.get(value)
    if group is None:
        try:
            if _verified(value) is None or os.getpgid(value.pid) != value.pid or os.getsid(value.pid) != value.pid:
                return
        except (*_GONE, *_DENIED, OSError):
            return
        with _lock:
            group = _groups.setdefault(value, _Group(value.pid, value.pid, {value}))
    with _lock:
        known = set(group.members)
    if not any(_session_matches(member, group) for member in known):
        return
    found: set[ProcessIdentity] = set()
    try:
        for process in _processes():
            try:
                if os.getpgid(process.pid) != group.pgid or os.getsid(process.pid) != group.sid:
                    continue
                member = ProcessIdentity(process.pid, process.create_time())
                if member.created >= value.created and _verified(member) is not None:
                    found.add(member)
            except (*_GONE, *_DENIED, OSError):
                continue
    except (*_DENIED, OSError):
        pass
    for member in known | found:
        try:
            found.update(_capture_descendants(member))
        except (*_GONE, *_DENIED, OSError):
            continue
    # 扫描期间锚点也可能退出；失去全部原锚点后不接纳新见到的数字组成员。
    if any(_session_matches(member, group) for member in known):
        with _lock:
            group.members.update(found)


def _protected() -> set[int]:
    try:
        return {os.getpid(), *(parent.pid for parent in psutil.Process().parents())}
    except (*_GONE, *_DENIED):
        # 无法确认调用者的祖先进程时，宁可不发任何终止信号。
        raise ProcessControlError("无法确认调用者进程树，已取消进程结束操作") from None


def _signal(value: ProcessIdentity, *, force: bool, protected: set[int]) -> bool:
    try:
        process = _verified(value)
        if process is None:
            return False
        if value.pid in protected:
            raise ProcessControlError("拒绝结束管理程序自身或其祖先进程")
        if force:
            process.kill()
        elif os.name == "nt":
            # 对 CREATE_NEW_PROCESS_GROUP 的控制台程序优先发中断；不支持时退回
            # Windows 的进程终止。POSIX 使用 SIGTERM，宽限期后才会强制结束。
            try:
                process.send_signal(signal.CTRL_BREAK_EVENT)
            except (OSError, ValueError):
                process.terminate()
        else:
            process.terminate()
        return True
    except _GONE:
        return False
    except (*_DENIED, OSError):
        raise ProcessControlError("权限不足，无法结束已确认的项目进程") from None


def _pending(values: set[ProcessIdentity] | list[ProcessIdentity]) -> list[ProcessIdentity]:
    try:
        return [value for value in values if _verified(value) is not None]
    except (*_DENIED, OSError):
        raise ProcessControlError("无法确认项目进程是否已经退出") from None


def terminate(identities: list[ProcessIdentity], grace: float = 10) -> None:
    """只结束仍匹配身份的进程及已确认后代；先请求退出，超时再强制结束。"""
    if not identities:
        return
    protected = _protected()
    targets = set(identities)
    if any(value.pid in protected and alive(value) for value in targets):
        raise ProcessControlError("拒绝结束管理程序自身或其祖先进程")
    deadline = time.monotonic() + max(0.0, grace)
    sent: set[ProcessIdentity] = set()
    while True:
        for root in identities:
            refresh_group(root)
            with _lock:
                if group := _groups.get(root):
                    targets.update(group.members)
        for value in list(targets):
            try:
                targets.update(_capture_descendants(value))
            except (*_DENIED, OSError):
                raise ProcessControlError("无法完整确认项目进程树，结束操作未完成") from None
        for value in targets - sent:
            _signal(value, force=False, protected=protected)
            sent.add(value)
        remaining = _pending(targets)
        if not remaining:
            return
        if time.monotonic() >= deadline:
            break
        time.sleep(min(0.05, max(0.0, deadline - time.monotonic())))
    for value in remaining:
        _signal(value, force=True, protected=protected)
    deadline = time.monotonic() + 2.0
    while _pending(remaining) and time.monotonic() < deadline:
        time.sleep(0.02)
    if _pending(remaining):
        raise ProcessControlError("仍有已确认的项目进程未退出")


def _unanchored_group_exists(value: ProcessIdentity) -> bool:
    """仅作告警检查；无身份锚点绝不结束新发现的组成员。"""
    try:
        # 明确看到 PID 被新进程占用时，那个新组不是原组。
        if psutil.Process(value.pid).create_time() != value.created:
            return False
    except _GONE:
        pass
    except _DENIED:
        raise ProcessControlError("无法确认原父进程身份") from None
    try:
        for process in _processes():
            try:
                if os.getpgid(process.pid) == value.pid and os.getsid(process.pid) == value.pid and _same_user(process):
                    if process.status() != psutil.STATUS_ZOMBIE:
                        return True
            except _GONE:
                continue
    except (*_DENIED, OSError):
        raise ProcessControlError("原父进程已退出，且无法确认残留进程组归属") from None
    return False


def terminate_group(pid: int, created: float, grace: float = 10) -> None:
    """结束新会话组；已退出父进程必须有先前记录的成员作为身份锚点。

    无锚点时不能把后来复用的数字 PGID 当作旧组。此函数不使用 killpg。
    """
    value = ProcessIdentity(pid, created)
    refresh_group(value)
    with _lock:
        group = _groups.get(value)
        members = set(group.members) if group else {value}
    terminate(list(members), grace)
    if os.name == "posix" and _unanchored_group_exists(value):
        raise ProcessControlError("原父进程已退出且没有已记录的存活成员，不能安全结束未知进程组")
    with _lock:
        _groups.pop(value, None)
