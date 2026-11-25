"""本机启动器 IPC。只控制持有本项目实例锁的守护，不发现或接管其他进程。

InstanceLock 必须由调用方在创建进程或 ControlServer 前持有，退出时最后释放。
运行记录含临时 IPC 凭据，只写入 data/run；业务配置仍在 avalon.toml。
"""
from __future__ import annotations

import errno
import http.client
import json
import math
import os
import secrets
import socket
import stat
import threading
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any, Callable
from urllib.parse import parse_qs, urlencode

PROTOCOL_VERSION = 1
MANIFEST_NAME = "launcher.json"
MAX_BODY = 8192
MAX_HEADERS = 16384
MAX_RESPONSE = 1024 * 1024
READ_TIMEOUT = 3.0
ACTIONS = frozenset({"status", "start", "stop", "restart", "reload", "down"})
TARGETS = frozenset({"backend", "nonebot", "goqbot", "web", "all"})


class ControlError(RuntimeError):
    """可直接向命令行使用者显示的控制错误，不包含 IPC 凭据。"""


class AlreadyRunningError(ControlError):
    pass


def _root(root: Path) -> Path:
    return Path(root).expanduser().resolve()


def _run_dir(root: Path) -> Path:
    directory = root / "data" / "run"
    directory.mkdir(parents=True, exist_ok=True, mode=0o700)
    return directory


def _payload(value: Any) -> dict[str, Any]:
    if not isinstance(value, dict) or set(value) - {"action", "targets", "enabled"}:
        raise ControlError("控制请求格式不正确")
    action = value.get("action")
    if not isinstance(action, str) or action not in ACTIONS:
        raise ControlError("不支持的控制操作")
    targets = value.get("targets", [])
    if (not isinstance(targets, list) or len(targets) > len(TARGETS)
            or any(not isinstance(t, str) or t not in TARGETS for t in targets)
            or len(set(targets)) != len(targets)
            or ("all" in targets and len(targets) != 1)):
        raise ControlError("控制目标须为 backend、nonebot、goqbot、web 或单独的 all")
    result = {"action": action, "targets": list(targets)}
    if "enabled" in value:
        if type(value["enabled"]) is not bool:
            raise ControlError("enabled 必须为布尔值")
        result["enabled"] = value["enabled"]
    return result


class InstanceLock:
    """非阻塞 OS 文件锁；不删除锁文件，避免旧 inode 与新 inode 同时被锁。"""

    def __init__(self, root: Path):
        self.root = _root(root)
        self._file = None

    def acquire(self) -> InstanceLock:
        if self._file is not None:
            return self
        path = _run_dir(self.root) / "launcher.lock"
        flags = os.O_RDWR | os.O_CREAT | getattr(os, "O_NOFOLLOW", 0)
        try:
            fd = os.open(path, flags, 0o600)
            stream = os.fdopen(fd, "r+b", buffering=0)
        except OSError as exc:
            raise ControlError("无法打开启动器实例锁，请检查 data/run 权限") from exc
        try:
            if not stat.S_ISREG(os.fstat(stream.fileno()).st_mode):
                raise ControlError("启动器实例锁必须是普通文件")
            if os.name == "nt":
                import msvcrt
                if os.fstat(stream.fileno()).st_size == 0:
                    stream.write(b"0")
                stream.seek(0)
                msvcrt.locking(stream.fileno(), msvcrt.LK_NBLCK, 1)
            else:
                import fcntl
                fcntl.flock(stream.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
        except OSError as exc:
            stream.close()
            if exc.errno in {errno.EACCES, errno.EAGAIN, errno.EDEADLK}:
                raise AlreadyRunningError("本项目已有启动器运行；请使用 status 查看或通过控制命令操作") from exc
            raise ControlError("无法获取启动器实例锁") from exc
        except BaseException:
            stream.close()
            raise
        self._file = stream
        return self

    def release(self) -> None:
        stream, self._file = self._file, None
        if stream is None:
            return
        try:
            if os.name == "nt":
                import msvcrt
                stream.seek(0)
                msvcrt.locking(stream.fileno(), msvcrt.LK_UNLCK, 1)
            else:
                import fcntl
                fcntl.flock(stream.fileno(), fcntl.LOCK_UN)
        finally:
            stream.close()

    def __enter__(self) -> InstanceLock:
        return self.acquire()

    def __exit__(self, *_: Any) -> None:
        self.release()


def _read_manifest(root: Path) -> dict[str, Any]:
    path = root / "data" / "run" / MANIFEST_NAME
    try:
        fd = os.open(path, os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0))
        with os.fdopen(fd, "rb") as stream:
            info = os.fstat(stream.fileno())
            if not stat.S_ISREG(info.st_mode) or info.st_size > MAX_BODY:
                raise ValueError
            if os.name != "nt" and info.st_mode & 0o077:
                raise ControlError("启动器运行凭据权限不安全；应仅允许当前用户读写（0600）")
            value = json.loads(stream.read(MAX_BODY + 1))
    except FileNotFoundError as exc:
        raise ControlError("本项目没有运行中的启动器；请先在项目根目录执行 uv run main.py") from exc
    except (OSError, ValueError, UnicodeError) as exc:
        raise ControlError("启动器运行记录无效；不会接管或停止其他服务") from exc
    if not isinstance(value, dict):
        raise ControlError("启动器运行记录无效")
    port, pid, created = value.get("port"), value.get("pid"), value.get("created_at")
    secret, identity = value.get("secret"), value.get("instance_id")
    valid = (type(value.get("protocol")) is int and value["protocol"] == PROTOCOL_VERSION
             and isinstance(value.get("root"), str)
             and os.path.normcase(value["root"]) == os.path.normcase(str(root))
             and type(port) is int and 1 <= port <= 65535
             and type(pid) is int and pid > 0
             and type(created) in (int, float) and math.isfinite(created)
             and 0 < created <= time.time() + 60
             and isinstance(secret, str) and len(secret) == 64
             and all(c in "0123456789abcdef" for c in secret)
             and isinstance(identity, str) and len(identity) == 32
             and all(c in "0123456789abcdef" for c in identity)
             and not any(key in value for key in ("host", "url", "endpoint")))
    if not valid:
        raise ControlError("启动器运行记录不属于本项目或协议无效；不会连接其他服务")
    return value


class _HeaderReader:
    def __init__(self, stream, budget: int):
        self.stream, self.remaining = stream, budget

    def readline(self, limit: int = -1):
        maximum = self.remaining + 1
        if limit >= 0:
            maximum = min(maximum, limit)
        line = self.stream.readline(maximum)
        self.remaining -= len(line)
        if self.remaining < 0:
            raise http.client.LineTooLong("header section")
        return line


class _HTTPServer(ThreadingHTTPServer):
    daemon_threads = True
    block_on_close = False
    request_queue_size = 8

    def __init__(self, owner: ControlServer):
        self.owner = owner
        self._slots = threading.BoundedSemaphore(16)
        super().__init__(("127.0.0.1", 0), _Handler)

    def process_request(self, request, client_address):
        if not self._slots.acquire(blocking=False):
            self.shutdown_request(request)
            return
        try:
            super().process_request(request, client_address)
        except BaseException:
            self._slots.release()
            raise

    def process_request_thread(self, request, client_address):
        try:
            super().process_request_thread(request, client_address)
        finally:
            self._slots.release()


class _Handler(BaseHTTPRequestHandler):
    protocol_version = "HTTP/1.1"
    server: _HTTPServer

    def setup(self):
        super().setup()
        self.connection.settimeout(READ_TIMEOUT)

    def log_message(self, *_):
        # 不记录请求行或认证头，避免临时凭据进入日志。
        pass

    def parse_request(self):
        if len(self.raw_requestline) > 2048:
            self.requestline = ""
            self.request_version = "HTTP/1.0"
            self.command = None
            self.send_error(414)
            return False
        stream = self.rfile
        self.rfile = _HeaderReader(stream, MAX_HEADERS)
        try:
            return super().parse_request()
        finally:
            self.rfile = stream

    def _send(self, code: int, result: dict):
        owner = self.server.owner
        data = json.dumps(result, ensure_ascii=False, allow_nan=False).encode("utf-8")
        # 即使 handler 误将运行记录纳入状态，也不传出此实例的 IPC 凭据。
        data = data.replace(owner._secret.encode("ascii"), b"[redacted]")
        if len(data) > MAX_RESPONSE:
            code, data = 500, b'{"ok":false,"error":"response too large"}'
        self.close_connection = True
        self.send_response(code)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(data)))
        self.send_header("Cache-Control", "no-store")
        self.send_header("Connection", "close")
        self.end_headers()
        self.wfile.write(data)
        self.wfile.flush()

    def _authorized(self) -> bool:
        owner = self.server.owner
        hosts = self.headers.get_all("Host", [])
        if hosts != [f"127.0.0.1:{owner.port}"] or self.headers.get_all("Origin"):
            self._send(403, {"ok": False, "error": "仅接受本机控制客户端"})
            return False
        auth = self.headers.get_all("Authorization", [])
        expected = ("Bearer " + owner._secret).encode("ascii")
        if len(auth) != 1 or not secrets.compare_digest(auth[0].encode("utf-8"), expected):
            self._send(401, {"ok": False, "error": "启动器认证失败，运行记录可能已过期"})
            return False
        if self.headers.get_all("X-Avalon-Instance", []) != [owner.instance_id]:
            self._send(409, {"ok": False, "error": "启动器实例已改变，请重新执行命令"})
            return False
        if self.headers.get_all("Transfer-Encoding") or self.headers.get_all("Expect"):
            self._send(400, {"ok": False, "error": "不支持的请求编码"})
            return False
        return True

    def _handle(self):
        owner = self.server.owner
        with owner._condition:
            if owner._closing:
                self._send(503, {"ok": False, "error": "启动器正在退出"})
                return
            owner._inflight += 1
        try:
            if not self._authorized():
                return
            if self.command == "GET":
                if self.headers.get("Content-Length", "0") != "0":
                    raise ControlError("GET 控制查询不接受请求体")
                if self.path == "/v1/handshake":
                    self._send(200, owner._identity())
                    return
                path, _, query = self.path.partition("?")
                if path != "/v1/status":
                    self._send(404, {"ok": False, "error": "不存在的控制接口"})
                    return
                try:
                    params = parse_qs(query, keep_blank_values=True, strict_parsing=True,
                                      max_num_fields=len(TARGETS))
                except ValueError as exc:
                    raise ControlError("status 查询参数格式不正确") from exc
                if set(params) - {"target"}:
                    raise ControlError("status 只接受 target 查询参数")
                payload = _payload({"action": "status", "targets": params.get("target", [])})
            else:
                if self.path != "/v1/action":
                    self._send(404, {"ok": False, "error": "不存在的控制接口"})
                    return
                lengths = self.headers.get_all("Content-Length", [])
                if len(lengths) != 1 or not lengths[0].isascii() or not lengths[0].isdigit():
                    raise ControlError("控制请求必须包含明确的 Content-Length")
                length = int(lengths[0])
                if length > MAX_BODY:
                    self._send(413, {"ok": False, "error": "控制请求过大"})
                    return
                if self.headers.get_content_type() != "application/json":
                    raise ControlError("控制请求须为 JSON")
                data = self.rfile.read(length)
                if len(data) != length:
                    raise ControlError("控制请求不完整")
                try:
                    payload = _payload(json.loads(data))
                except (ValueError, UnicodeError) as exc:
                    raise ControlError("控制请求不是有效的 JSON") from exc
                if payload["action"] == "status":
                    raise ControlError("status 只允许通过 GET 查询")
            result = owner.handler(payload)
            if not isinstance(result, dict):
                raise ControlError("启动器控制处理器返回了无效结果")
            self._send(200, result)
        except ControlError as exc:
            self._send(400, {"ok": False, "error": str(exc)})
        except (BrokenPipeError, ConnectionResetError, socket.timeout):
            pass
        except Exception:
            self._send(500, {"ok": False, "error": "启动器处理命令失败，请检查运行日志"})
        finally:
            with owner._condition:
                owner._inflight -= 1
                owner._condition.notify_all()

    do_GET = _handle
    do_POST = _handle

    def _unsupported(self):
        if self._authorized():
            self._send(405, {"ok": False, "error": "不支持的控制请求方法"})

    do_PUT = do_DELETE = do_PATCH = do_OPTIONS = do_HEAD = do_TRACE = do_CONNECT = _unsupported


class ControlServer:
    def __init__(self, root: Path, handler: Callable[[dict], dict]):
        self.root = _root(root)
        self.handler = handler
        self.instance_id = secrets.token_hex(16)
        self._secret = secrets.token_hex(32)
        self._created_at = time.time()
        self._server: _HTTPServer | None = None
        self._thread: threading.Thread | None = None
        self._condition = threading.Condition()
        self._inflight = 0
        self._closing = False
        self.port = 0

    def _identity(self) -> dict:
        return {"protocol": PROTOCOL_VERSION, "root": str(self.root), "pid": os.getpid(),
                "created_at": self._created_at, "instance_id": self.instance_id}

    def start(self) -> ControlServer:
        if self._server is not None:
            return self
        if self._closing:
            raise ControlError("已关闭的控制实例不能再次启动")
        path = _run_dir(self.root) / MANIFEST_NAME
        server = _HTTPServer(self)
        self._server = server
        self.port = server.server_address[1]
        temporary = path.with_name(f".{MANIFEST_NAME}.{self.instance_id}.tmp")
        try:
            fd = os.open(temporary, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
            with os.fdopen(fd, "w", encoding="utf-8") as stream:
                json.dump({**self._identity(), "port": self.port, "secret": self._secret}, stream)
                stream.flush()
                os.fsync(stream.fileno())
            os.chmod(temporary, 0o600)
            os.replace(temporary, path)
            self._thread = threading.Thread(target=server.serve_forever, kwargs={"poll_interval": .05},
                                            name="avalon-control", daemon=True)
            self._thread.start()
        except BaseException:
            temporary.unlink(missing_ok=True)
            server.server_close()
            self._server = None
            self._remove_manifest()
            raise
        return self

    def _remove_manifest(self):
        try:
            value = _read_manifest(self.root)
            if value["instance_id"] == self.instance_id and value["secret"] == self._secret:
                (self.root / "data" / "run" / MANIFEST_NAME).unlink(missing_ok=True)
        except ControlError:
            pass

    def close(self) -> None:
        server, self._server = self._server, None
        if server is None:
            return
        with self._condition:
            self._closing = True
        server.shutdown()
        deadline = time.monotonic() + 1.0
        with self._condition:
            while self._inflight and (left := deadline - time.monotonic()) > 0:
                self._condition.wait(left)
        server.server_close()
        if self._thread is not threading.current_thread():
            self._thread.join(timeout=1)
        self._remove_manifest()

    def __enter__(self) -> ControlServer:
        return self.start()

    def __exit__(self, *_: Any) -> None:
        self.close()


def request(root: Path, payload: dict, timeout: float = 5.0) -> dict:
    """认证后连接固定回环地址；不使用 HTTP_PROXY，不接受记录中的任意 URL。"""
    root, payload = _root(root), _payload(payload)
    if type(timeout) not in (int, float) or not math.isfinite(timeout) or timeout <= 0:
        raise ControlError("控制请求超时必须为正数")
    manifest = _read_manifest(root)
    headers = {"Host": f"127.0.0.1:{manifest['port']}",
               "Authorization": "Bearer " + manifest["secret"],
               "X-Avalon-Instance": manifest["instance_id"]}

    def exchange(method: str, path: str, body: bytes | None = None) -> dict:
        connection = http.client.HTTPConnection("127.0.0.1", manifest["port"], timeout=timeout)
        try:
            connection.request(method, path, body, {**headers, "Content-Type": "application/json"})
            response = connection.getresponse()
            data = response.read(MAX_RESPONSE + 1)
            if len(data) > MAX_RESPONSE:
                raise ControlError("启动器响应过大")
            try:
                result = json.loads(data)
            except (ValueError, UnicodeError) as exc:
                raise ControlError("启动器响应格式不正确；不会接管其他服务") from exc
            if not isinstance(result, dict):
                raise ControlError("启动器响应格式不正确")
            if response.status != 200:
                message = result.get("error")
                if not isinstance(message, str):
                    message = "启动器拒绝了控制请求"
                raise ControlError(message.replace(manifest["secret"], "[redacted]"))
            return result
        except (OSError, http.client.HTTPException) as exc:
            raise ControlError("无法连接本项目启动器，运行记录可能已过期；不会接管或停止其他服务") from exc
        finally:
            connection.close()

    identity = exchange("GET", "/v1/handshake")
    if any(identity.get(key) != manifest[key] for key in
           ("protocol", "root", "pid", "created_at", "instance_id")):
        raise ControlError("启动器握手不匹配，运行记录已过期；请重新执行命令")
    if payload["action"] == "status":
        query = urlencode([("target", target) for target in payload["targets"]])
        return exchange("GET", "/v1/status" + ("?" + query if query else ""))
    return exchange("POST", "/v1/action", json.dumps(payload).encode("utf-8"))
