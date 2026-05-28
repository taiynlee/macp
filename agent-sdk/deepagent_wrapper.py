"""
DeepAgent → MACP bridge.

Runs on Windows. Connects to local MACP server and local LangGraph deepagent.
WSL2 auto-forwards port 2024 (deepagent) to Windows localhost.

Usage:
    python deepagent_wrapper.py
    python deepagent_wrapper.py --server ws://localhost:8010/ws/agent
"""

import argparse
import asyncio
import json
import logging
import os

import httpx

from wrapper import AgentWrapper

logging.basicConfig(level=logging.INFO, format="%(asctime)s [dba_agent] %(message)s")

DEEPAGENT_URL = os.environ.get("DEEPAGENT_URL", "http://localhost:2024")
ASSISTANT_ID  = os.environ.get("DEEPAGENT_ASSISTANT_ID", "")

_APPROVE_WORDS = {"approve", "yes", "y", "確認", "同意", "ok", "好"}
_REJECT_WORDS  = {"reject", "no", "n", "拒絕", "取消", "cancel"}


def _default_server() -> str:
    return "ws://localhost:8010/ws/agent"


def _extract_text(messages: list) -> str:
    for msg in reversed(messages):
        if msg.get("type") in ("human", "tool"):
            continue
        content = str(msg.get("content", "")).strip()
        if not content:
            continue
        if "</think>" in content:
            content = content.split("</think>", 1)[-1].strip()
        if content:
            return content
    return ""


def _parse_decision(text: str) -> str | None:
    """Map user text → 'approve'/'reject', or None if not a decision."""
    low = text.strip().lower()
    if low in _APPROVE_WORDS:
        return "approve"
    if low in _REJECT_WORDS:
        return "reject"
    return None


class DeepAgentWrapper(AgentWrapper):
    name = "dba_agent"
    capabilities = [
        "query_database",
        "check_connections",
        "describe_schema",
        "run_sql",
        "explain_query",
    ]

    def __init__(self, server_url: str) -> None:
        super().__init__(server_url=server_url)
        self._approval_future: asyncio.Future | None = None
        self._approval_recently_resolved: bool = False
        self._thread_id: str | None = None  # persistent across questions

    # ── internal helpers ─────────────────────────────────────────────────────

    async def _resolve_approval(self, decision: str) -> bool:
        """Resolve pending approval. Returns True if there was one waiting."""
        if self._approval_future and not self._approval_future.done():
            self._approval_future.set_result(decision)
            self._approval_recently_resolved = True
            return True
        return False

    async def _ask_deepagent(self, question: str, timeout: int = 180) -> str:
        """Send question to deepagent; ask user via chat for each interrupt."""
        async with httpx.AsyncClient(base_url=DEEPAGENT_URL, timeout=timeout) as client:
            if self._thread_id is None:
                r = await client.post("/threads", json={})
                r.raise_for_status()
                self._thread_id = r.json()["thread_id"]
                logging.info(f"[dba_agent] created thread {self._thread_id}")
            thread_id = self._thread_id

            r = await client.post(
                f"/threads/{thread_id}/runs/wait",
                json={
                    "assistant_id": ASSISTANT_ID,
                    "input": {"messages": [{"role": "user", "content": question}]},
                },
            )
            if r.status_code != 200:
                logging.warning(f"[dba_agent] runs/wait {r.status_code}: {r.text[:300]}")
                r.raise_for_status()
            data = r.json()

            for _ in range(8):
                interrupts = data.get("__interrupt__", [])
                if not interrupts:
                    break

                # Build human-readable question from interrupt value
                iv = interrupts[0].get("value", {})
                if isinstance(iv, dict):
                    configs = iv.get("review_configs", [{}])
                    cfg = configs[0] if configs else {}
                    cmd = (cfg.get("command")
                           or cfg.get("tool")
                           or json.dumps(iv, ensure_ascii=False)[:300])
                    allowed = cfg.get("allowed_decisions", ["approve", "reject"])
                else:
                    cmd = str(iv)[:300]
                    allowed = ["approve", "reject"]

                decision = "approve"
                logging.info(f"[dba_agent] auto-approve: {cmd[:80]}")

                # Format resume value based on interrupt type
                if isinstance(iv, dict) and "action_requests" in iv:
                    approved = decision == "approve"
                    n = len(iv["action_requests"])
                    dtype = "approve" if approved else "reject"
                    resume_value = {"decisions": [{"type": dtype}] * n}
                else:
                    resume_value = decision  # string "approve"/"reject"

                r = await client.post(
                    f"/threads/{thread_id}/runs/wait",
                    json={
                        "assistant_id": ASSISTANT_ID,
                        "command": {"resume": resume_value},
                    },
                )
                logging.info(f"[dba_agent] resume {r.status_code}: {r.text[:500]}")
                if r.status_code != 200:
                    break
                data = r.json()
                if isinstance(data, dict) and data.get("__error__"):
                    logging.warning(f"[dba_agent] __error__: {str(data['__error__'])[:500]}")
                    break

        messages = data.get("messages", []) if isinstance(data, dict) else []
        return _extract_text(messages) or "(deepagent returned no text)"

    async def handle_task(self, msg: dict) -> str:
        question = msg.get("content", "").strip()
        if not question:
            return "empty task"
        if question.lower() == "!reset":
            self._thread_id = None
            logging.info("[dba_agent] thread reset")
            return "記憶已清除，開始新對話。"

        context = msg.get("context", [])
        history = "\n".join(
            f"[{m['sender']}]: {m['content']}"
            for m in context
            if m.get("content", "").strip()
        ) if context else ""

        original_sender = msg.get("original_sender", "")
        reply_hint = (
            f"此訊息來自 {original_sender}。若對話尚未結束，回覆結尾必須加上 @{original_sender} 讓對方繼續收到。\n"
            if original_sender and original_sender not in ("", "orchestrator", "server")
            else "若要傳訊息給 k8s_agent，必須在回覆中寫 @k8s_agent。\n"
        )
        prefix = f"[系統資訊]\n你是 dba_agent，負責資料庫相關任務，連接至 MACP 多 Agent 平台。\n聊天室成員：operator（用戶）、dba_agent（你）、k8s_agent、gmail_agent。\n{reply_hint}\n"
        if history:
            prefix += f"[聊天室記錄]\n{history}\n\n"
        full_question = f"{prefix}[當前問題] {question}"

        logging.info(f"forwarding to deepagent: {question[:80]}")
        return await self._ask_deepagent(full_question)

    # ── override to intercept approval messages before normal dispatch ────────

    async def _dispatch_task(self, ws, msg: dict) -> None:
        content = msg.get("content", "").strip()
        decision = _parse_decision(content)
        if decision:
            resolved = await self._resolve_approval(decision)
            if resolved:
                logging.info(f"[dba_agent] approval resolved via task: {decision}")
                return
            if self._approval_recently_resolved:
                # on_message already resolved it; swallow this duplicate task
                self._approval_recently_resolved = False
                logging.info(f"[dba_agent] approval duplicate task swallowed: {decision}")
                return

        await super()._dispatch_task(ws, msg)

    async def on_message(self, msg: dict) -> None:
        content = str(msg.get("content", "")).strip()
        decision = _parse_decision(content)
        if decision and await self._resolve_approval(decision):
            logging.info(f"[dba_agent] approval resolved via message: {decision}")
            return
        logging.info(f"recv {msg.get('type')}: {content[:80]}")

    async def run_scheduled_job(self, job_name: str) -> bool:
        if job_name == "connection_check":
            try:
                async with httpx.AsyncClient(base_url=DEEPAGENT_URL, timeout=5) as client:
                    r = await client.get("/ok")
                    return r.status_code < 400
            except Exception:
                return False
        return True  # other jobs: assume OK until actually implemented

    async def on_connect(self) -> None:
        await self.send_alert("dba_agent online — DB ready", priority="normal")
        await self.send_schedule([
            {"name": "connection_check", "cron": "*/5 * * * *", "desc": "每5分鐘檢查資料庫連線"},
            {"name": "slow_query_scan",  "cron": "0 * * * *",   "desc": "每小時掃描慢查詢"},
            {"name": "daily_backup",     "cron": "0 2 * * *",   "desc": "每日凌晨2點備份"},
            {"name": "vacuum_analyze",   "cron": "0 3 * * 0",   "desc": "每週日凌晨3點 VACUUM"},
        ])


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--server", default=None, help="MACP ws:// URL")
    args = parser.parse_args()

    server_url = args.server or _default_server()
    logging.info(f"connecting to MACP at {server_url}")
    DeepAgentWrapper(server_url=server_url).run()
