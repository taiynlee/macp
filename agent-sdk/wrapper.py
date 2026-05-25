"""
AgentWrapper — base class for all MACP agents.

Usage:
    class MyAgent(AgentWrapper):
        name = "my_agent"
        capabilities = ["do_something"]

        async def handle_task(self, msg: dict) -> str:
            return "done"

    MyAgent(server_url="ws://localhost:8000/ws/agent").run()
"""

import asyncio
import json
import logging
import uuid
from abc import ABC, abstractmethod
from datetime import datetime, timezone

import websockets
from websockets.exceptions import ConnectionClosed

logger = logging.getLogger(__name__)

HEARTBEAT_INTERVAL = 30   # seconds
RECONNECT_BASE     = 2    # seconds
RECONNECT_MAX      = 60   # seconds


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _msg(**kwargs) -> str:
    kwargs.setdefault("id", str(uuid.uuid4()))
    kwargs.setdefault("timestamp", _now())
    return json.dumps(kwargs)


class AgentWrapper(ABC):
    name: str
    capabilities: list[str] = []

    def __init__(self, server_url: str) -> None:
        # server_url example: ws://192.168.1.10:8000/ws/agent
        self._url = f"{server_url}?name={self.name}"
        self._ws = None
        self._running = False
        self._jobs: list[dict] = []

    # ── override this ────────────────────────────────────────────────────────

    @abstractmethod
    async def handle_task(self, msg: dict) -> str:
        """Receive a task message, return result string."""

    # ── optional hooks ───────────────────────────────────────────────────────

    async def on_connect(self) -> None:
        """Called after successful connect + register."""

    async def on_disconnect(self) -> None:
        """Called on disconnect before reconnect attempt."""

    async def on_message(self, msg: dict) -> None:
        """Called for every non-task, non-system message (discussion, alert…)."""

    # ── public ───────────────────────────────────────────────────────────────

    def run(self) -> None:
        asyncio.run(self._run_loop())

    async def send(self, **kwargs) -> None:
        """Send arbitrary message to server."""
        if self._ws:
            kwargs.setdefault("sender", self.name)
            await self._ws.send(_msg(**kwargs))

    async def send_alert(self, content: str, priority: str = "high") -> None:
        await self.send(type="alert", content=content, priority=priority, target="all")

    async def send_schedule(self, jobs: list[dict]) -> None:
        self._jobs = jobs
        await self.send(type="system", action="set_schedule", jobs=jobs)

    async def report_job(self, job_name: str, success: bool) -> None:
        await self.send(type="system", action="job_result", job=job_name, success=success)

    async def run_scheduled_job(self, job_name: str) -> bool:
        """Override to implement actual job logic. Return True = success."""
        return True

    # ── internals ────────────────────────────────────────────────────────────

    async def _run_loop(self) -> None:
        self._running = True
        attempt = 0
        while self._running:
            try:
                await self._connect_and_serve()
                attempt = 0
            except Exception as exc:
                delay = min(RECONNECT_BASE * 2 ** attempt, RECONNECT_MAX)
                logger.warning(f"[{self.name}] disconnected ({exc}), retry in {delay}s")
                await self.on_disconnect()
                await asyncio.sleep(delay)
                attempt += 1

    async def _connect_and_serve(self) -> None:
        async with websockets.connect(self._url) as ws:
            self._ws = ws
            logger.info(f"[{self.name}] connected")

            await self._register(ws)
            await self.on_connect()

            hb_task  = asyncio.create_task(self._heartbeat_loop(ws))
            job_task = asyncio.create_task(self._job_scheduler())
            try:
                await self._recv_loop(ws)
            finally:
                hb_task.cancel()
                job_task.cancel()
                self._ws = None

    async def _register(self, ws) -> None:
        await ws.send(_msg(
            type="system",
            action="register",
            sender=self.name,
            capabilities=self.capabilities,
        ))
        raw = await ws.recv()
        resp = json.loads(raw)
        if resp.get("action") == "registered":
            logger.info(f"[{self.name}] registered OK")
        else:
            logger.warning(f"[{self.name}] unexpected register response: {resp}")

    @staticmethod
    def _cron_interval(cron: str) -> int | None:
        """Parse simple cron to seconds. Handles */N and 0 * patterns only."""
        parts = cron.strip().split()
        if len(parts) != 5:
            return None
        m, h, dom, mon, dow = parts
        stars = all(x == "*" for x in [dom, mon, dow])
        if not stars:
            return None
        if m.startswith("*/") and h == "*":
            try: return int(m[2:]) * 60
            except ValueError: return None
        if m == "0" and h.startswith("*/"):
            try: return int(h[2:]) * 3600
            except ValueError: return None
        if m == "0" and h == "*":
            return 3600
        return None

    async def _job_scheduler(self) -> None:
        try:
            # track next-run time per job
            intervals: dict[str, int] = {}
            counters:  dict[str, int] = {}
            for job in self._jobs:
                secs = self._cron_interval(job.get("cron", ""))
                if secs:
                    intervals[job["name"]] = secs
                    counters[job["name"]]  = secs  # first run after one full interval

            if not intervals:
                return

            while True:
                await asyncio.sleep(1)
                for name, secs in intervals.items():
                    counters[name] -= 1
                    if counters[name] <= 0:
                        counters[name] = secs
                        logger.info(f"[{self.name}] running scheduled job: {name}")
                        try:
                            success = await self.run_scheduled_job(name)
                        except Exception as exc:
                            logger.warning(f"[{self.name}] job {name} error: {exc}")
                            success = False
                        await self.report_job(name, success)
        except asyncio.CancelledError:
            pass

    async def _heartbeat_loop(self, ws) -> None:
        try:
            while True:
                await asyncio.sleep(HEARTBEAT_INTERVAL)
                await ws.send(_msg(
                    type="system",
                    action="heartbeat",
                    sender=self.name,
                ))
        except (ConnectionClosed, asyncio.CancelledError):
            pass

    async def _recv_loop(self, ws) -> None:
        async for raw in ws:
            try:
                msg = json.loads(raw)
            except json.JSONDecodeError:
                logger.warning(f"[{self.name}] bad JSON: {raw}")
                continue

            msg_type = msg.get("type")
            target = msg.get("target", "all")

            if msg_type == "task":
                if target in ("all", self.name):
                    asyncio.create_task(self._dispatch_task(ws, msg))
            elif msg_type == "system":
                pass  # server-side system messages; nothing to do
            else:
                await self.on_message(msg)

    async def _dispatch_task(self, ws, msg: dict) -> None:
        task_id = msg.get("id", "unknown")
        logger.info(f"[{self.name}] received task {task_id}")
        try:
            result = await self.handle_task(msg)
        except Exception as exc:
            result = f"ERROR: {exc}"
            logger.exception(f"[{self.name}] task {task_id} failed")

        await ws.send(_msg(
            type="report",
            sender=self.name,
            target=msg.get("sender", "orchestrator"),
            content=result,
            task_id=task_id,
            priority=msg.get("priority", "normal"),
        ))
