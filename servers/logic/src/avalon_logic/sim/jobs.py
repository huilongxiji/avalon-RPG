"""有界进程队列。任务及报告存到独立 sim/jobs.db，绝不连接 game.db / stats.db。"""

from __future__ import annotations

import asyncio
import json
import logging
import multiprocessing
import os
import secrets
import sqlite3
import time
from contextlib import suppress
from pathlib import Path

from avalon_contracts.api.sim import SimJobInfo, SimJobRequest
from avalon_contracts.errors import GameError

from . import compute
from .snapshot import DATA

log = logging.getLogger("avalon_logic.sim")
TERMINAL = {"finished", "failed", "cancelled"}


def _worker(pipe, snapshot: dict, version: int, digest: str, body: dict):
    try:
        if hasattr(os, "nice"):
            with suppress(OSError):  # 某些桌面沙箱不允许调整优先级，仍可在有界进程里正常运行。
                os.nice(5)
        report = compute.run(snapshot, version, digest, body,
                             lambda done, total: pipe.send(("progress", done, total)))
        pipe.send(("finished", report))
    except Exception as exc:
        log.exception("模拟计算失败")
        pipe.send(("failed", f"模拟计算失败：{type(exc).__name__}；请检查规则或缩小场景"))
    finally:
        pipe.close()


class JobQueue:
    def __init__(self, path: Path, *, workers: int = 2, timeout: float = 600):
        path.parent.mkdir(parents=True, exist_ok=True)
        self.db = sqlite3.connect(path)
        self.db.row_factory = sqlite3.Row
        self.db.execute("PRAGMA journal_mode=WAL")
        self.db.execute("""CREATE TABLE IF NOT EXISTS jobs (
            id INTEGER PRIMARY KEY AUTOINCREMENT, owner TEXT NOT NULL, status TEXT NOT NULL,
            info TEXT NOT NULL, request TEXT NOT NULL, snapshot TEXT NOT NULL, report TEXT
        )""")
        self.db.commit()
        self.workers, self.timeout = workers, timeout
        self._runner: asyncio.Task | None = None
        self._running: dict[int, asyncio.Task] = {}
        self._processes: dict[int, multiprocessing.Process] = {}
        self._stopping = False
        # 不自动重跑，避免重启后悄悄消耗资源或套用修改过的草稿。
        for row in self.db.execute("SELECT id, info FROM jobs WHERE status IN ('queued', 'running')").fetchall():
            info = SimJobInfo.model_validate_json(row["info"])
            info.status, info.message = "failed", "服务上次退出时任务未完成，请重新提交"
            self._save(info)

    def start(self):
        if self._runner is None:
            self._runner = asyncio.create_task(self._schedule(), name="simulation-queue")

    async def stop(self):
        self._stopping = True
        if self._runner is not None:
            self._runner.cancel()
            await asyncio.gather(self._runner, return_exceptions=True)
            self._runner = None
        for task in list(self._running.values()):
            task.cancel()
        await asyncio.gather(*list(self._running.values()), return_exceptions=True)
        for row in self.db.execute("SELECT info FROM jobs WHERE status IN ('queued', 'running')").fetchall():
            info = SimJobInfo.model_validate_json(row["info"])
            info.status, info.message = "failed", "服务已停止，请重新提交任务"
            self._save(info)
        self.db.close()

    def _save(self, info: SimJobInfo, report: dict | None = None):
        self.db.execute("UPDATE jobs SET status=?, info=?, report=COALESCE(?, report) WHERE id=?",
                        (info.status, info.model_dump_json(), json.dumps(report, ensure_ascii=False)
                         if report is not None else None, info.id))
        self.db.commit()

    def _row(self, job_id: int, owner: str | None = None):
        row = self.db.execute("SELECT * FROM jobs WHERE id=?", (job_id,)).fetchone()
        if row is None or (owner is not None and row["owner"] != owner):
            raise GameError("not_found", "模拟任务不存在")
        return row

    def get(self, job_id: int, owner: str | None = None) -> SimJobInfo:
        return SimJobInfo.model_validate_json(self._row(job_id, owner)["info"])

    def list(self, owner: str, limit: int = 50) -> list[SimJobInfo]:
        rows = self.db.execute("SELECT info FROM jobs WHERE owner=? ORDER BY id DESC LIMIT ?", (owner, limit))
        return [SimJobInfo.model_validate_json(row["info"]) for row in rows]

    def report(self, job_id: int, owner: str) -> dict:
        row = self._row(job_id, owner)
        if row["status"] != "finished":
            raise GameError("conflict", "任务尚未成功完成，暂时没有报告", status=row["status"])
        return json.loads(row["report"])

    def submit(self, owner: str, body: SimJobRequest, version: int, digest: str, snapshot: dict) -> SimJobInfo:
        if self._stopping:
            raise GameError("logic_unavailable", "模拟队列正在停止")
        waiting = self.db.execute("SELECT COUNT(*) FROM jobs WHERE status IN ('queued', 'running')").fetchone()[0]
        if waiting >= 32:
            raise GameError("rate_limited", "模拟队列已满，请稍后重试")
        if body.type == "world_boss" and not body.targets:
            body = body.model_copy(update={"targets": ["world_boss"]})
        compute.validate(DATA.validate_python(snapshot).compile(version), body)
        body = body.model_copy(update={"seed": body.seed if body.seed is not None else secrets.randbits(48)})
        info = SimJobInfo(id=0, type=body.type, status="queued", name=body.name,
                          rules_version=version, rules_digest=digest, seed=body.seed,
                          total=body.runs * len(body.loadouts) * len(body.targets))
        cursor = self.db.execute("INSERT INTO jobs(owner,status,info,request,snapshot) VALUES(?,?,?,?,?)",
                                 (owner, info.status, info.model_dump_json(), body.model_dump_json(),
                                  json.dumps(snapshot, ensure_ascii=False)))
        info.id = cursor.lastrowid
        self._save(info)
        return info

    def cancel(self, job_id: int, owner: str) -> SimJobInfo:
        info = self.get(job_id, owner)
        if info.status not in TERMINAL:
            # 先写终态；工作进程随后返回的结果不能覆盖取消。
            info.status, info.message = "cancelled", "任务已取消"
            self._save(info)
            if task := self._running.get(job_id):
                task.cancel()
        return info

    async def wait(self, job_id: int, owner: str, seconds: float = 20) -> SimJobInfo:
        deadline = time.monotonic() + seconds
        while True:
            info = self.get(job_id, owner)
            if info.status in TERMINAL or time.monotonic() >= deadline:
                return info
            await asyncio.sleep(.05)

    async def _schedule(self):
        while not self._stopping:
            self._running = {key: task for key, task in self._running.items() if not task.done()}
            free = self.workers - len(self._running)
            if free > 0:
                rows = self.db.execute("SELECT id FROM jobs WHERE status='queued' ORDER BY id LIMIT ?", (free,))
                for row in rows.fetchall():
                    job_id = row["id"]
                    info = self.get(job_id)
                    info.status = "running"
                    self._save(info)
                    self._running[job_id] = asyncio.create_task(self._execute(job_id))
            await asyncio.sleep(.05)

    async def _execute(self, job_id: int):
        context = multiprocessing.get_context("spawn")
        receive, send = context.Pipe(duplex=False)
        row, info = self._row(job_id), self.get(job_id)
        process = context.Process(target=_worker, args=(send, json.loads(row["snapshot"]), info.rules_version,
                                                        info.rules_digest, json.loads(row["request"])), daemon=True)
        try:
            process.start()
            self._processes[job_id] = process
            send.close()
            started = time.monotonic()
            while True:
                if self.get(job_id).status in TERMINAL:
                    return
                if time.monotonic() - started > self.timeout:
                    raise TimeoutError("任务超过运行时限")
                if receive.poll():
                    message = receive.recv()
                    if message[0] == "progress":
                        info.completed, info.total = message[1:]
                        info.progress = info.completed / info.total
                        self._save(info)
                    elif message[0] == "finished":
                        info.status, info.progress, info.completed = "finished", 1, info.total
                        self._save(info, message[1])
                        return
                    else:
                        info.status, info.message = "failed", message[1]
                        self._save(info)
                        return
                elif not process.is_alive():
                    raise RuntimeError("模拟进程意外退出")
                await asyncio.sleep(.02)
        except asyncio.CancelledError:
            raise
        except Exception as exc:
            log.exception("模拟任务 %s 失败", job_id)
            if self.get(job_id).status not in TERMINAL:
                info.status = "failed"
                info.message = "任务超过 10 分钟运行时限，请缩小场景" if isinstance(exc, TimeoutError) else "模拟进程异常退出，请重新提交"
                self._save(info)
        finally:
            async def cleanup():
                if process.pid is not None:
                    if process.is_alive():
                        process.terminate()
                    await asyncio.to_thread(process.join, 2)
                    if process.is_alive():
                        process.kill()
                        await asyncio.to_thread(process.join)
                    process.close()
                receive.close()
                send.close()
                self._processes.pop(job_id, None)

            # 取消和服务退出可能重叠；第二次取消也必须等子进程回收完成。
            cleanup_task = asyncio.create_task(cleanup())
            try:
                await asyncio.shield(cleanup_task)
            except asyncio.CancelledError:
                await cleanup_task
                raise


_queue: JobQueue | None = None


def queue() -> JobQueue:
    if _queue is None:
        raise GameError("logic_unavailable", "模拟队列尚未启动")
    return _queue
