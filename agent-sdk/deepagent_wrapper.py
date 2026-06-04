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
from pathlib import Path

import httpx

from wrapper import AgentWrapper

_SCHEDULE_FILE = Path(__file__).parent / "dba_schedule.json"

logging.basicConfig(level=logging.INFO, format="%(asctime)s [dba_agent] %(message)s")

DEEPAGENT_URL = os.environ.get("DEEPAGENT_URL", "http://localhost:2024")
ASSISTANT_ID  = os.environ.get("DEEPAGENT_ASSISTANT_ID", "")

_APPROVE_WORDS = {"approve", "yes", "y", "確認", "同意", "ok", "好"}
_REJECT_WORDS  = {"reject", "no", "n", "拒絕", "取消", "cancel"}

_DEFAULT_SCHEDULE = [
    {"name": "connection_check", "cron": "*/5 * * * *", "desc": "Ping LangGraph /ok"},
]

_DEFAULT_CAPABILITIES = ["postgres", "gh-tool", "git-tool", "remember", "skill-creator"]


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
    capabilities = []  # populated dynamically from LangGraph on connect

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
            for attempt in range(2):
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
                if r.status_code == 404 and attempt == 0:
                    logging.warning(f"[dba_agent] thread {thread_id} expired, creating new one")
                    self._thread_id = None
                    continue
                if r.status_code != 200:
                    logging.warning(f"[dba_agent] runs/wait {r.status_code}: {r.text[:300]}")
                    r.raise_for_status()
                break
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

        if question.startswith("!schedule"):
            payload = question[len("!schedule"):].strip()

            def _save(jobs: list) -> str:
                _SCHEDULE_FILE.write_text(
                    json.dumps(jobs, ensure_ascii=False, indent=2), encoding="utf-8"
                )

            async def _apply(jobs: list) -> str:
                await self.send_schedule(jobs)
                _save(jobs)
                return json.dumps(jobs, ensure_ascii=False, indent=2)

            # !schedule  → 顯示目前排程
            if not payload:
                current = json.dumps(self._jobs, ensure_ascii=False, indent=2) if self._jobs else "（尚無排程）"
                return (
                    f"目前排程：\n{current}\n\n"
                    "指令：\n"
                    "  !schedule add {\"name\":\"...\",\"cron\":\"...\",\"desc\":\"...\"}\n"
                    "  !schedule remove <job名稱>\n"
                    "  !schedule [...]  （整批替換）"
                )

            # !schedule add {...}  → 新增單一 job
            if payload.startswith("add "):
                try:
                    new_job = json.loads(payload[4:].strip())
                    if not isinstance(new_job, dict) or not new_job.get("name") or not new_job.get("cron"):
                        return "格式錯誤，需要 {\"name\":\"...\",\"cron\":\"...\",\"desc\":\"...\"}"
                    jobs = [j for j in self._jobs if j.get("name") != new_job["name"]]
                    jobs.append(new_job)
                    result = await _apply(jobs)
                    return f"已新增 {new_job['name']}，目前共 {len(jobs)} 個排程：\n{result}"
                except Exception as e:
                    return f"新增失敗：{e}"

            # !schedule remove <name>  → 移除單一 job
            if payload.startswith("remove "):
                name = payload[7:].strip()
                jobs = [j for j in self._jobs if j.get("name") != name]
                if len(jobs) == len(self._jobs):
                    return f"找不到排程：{name}"
                result = await _apply(jobs)
                return f"已移除 {name}，目前共 {len(jobs)} 個排程：\n{result}"

            # !schedule [...]  → 整批替換
            try:
                jobs = json.loads(payload)
                if not isinstance(jobs, list):
                    return "格式錯誤，請傳入 JSON array。"
                result = await _apply(jobs)
                return f"排程已整批更新，共 {len(jobs)} 個任務：\n{result}"
            except Exception as e:
                return f"排程解析失敗：{e}"

        context = msg.get("context", [])
        history = "\n".join(
            f"[{m['sender']}]: {m['content']}"
            for m in context
            if m.get("content", "").strip()
        ) if context else ""

        original_sender = msg.get("original_sender", "")
        reply_hint = (
            f"此訊息來自 {original_sender}。若對話尚未結束需要對方繼續配合，才在回覆結尾加上 @{original_sender}；若已回答完畢則不需要。\n"
            if original_sender and original_sender not in ("", "orchestrator", "server")
            else ""
        )
        rules = (
            "行為規則：\n"
            "1. 可以閒聊、自我介紹、聊興趣或工作，回應要自然簡短。\n"
            "2. 【重要】想對某個 agent 說話或發問，訊息中必須包含 @完整名稱（如 @k8s_agent、@gmail_agent）。\n"
            "   沒有 @ 對方就不會收到你的訊息。例如：「@k8s_agent 叢集最近還好嗎？」\n"
            "3. 若某個 agent @你，你可以回覆，但回覆後不要再 @任何人，避免無限對話。\n"
            "4. 不要同時 @多個 agent 製造群聊迴圈。\n"
            "5. 禁止無意義的回覆，例如：好的、收到、👍、再見。\n"
        )
        schedule_desc = "、".join(
            f"{j['name']}（{j.get('desc', j['cron'])}）" for j in self._jobs
        ) if self._jobs else "（尚未設定）"
        prefix = f"[目前排程] {json.dumps(self._jobs, ensure_ascii=False)}\n"
        if reply_hint:
            prefix += reply_hint
        if history:
            prefix += f"[聊天室記錄]\n{history}\n\n"
        full_question = f"{prefix}[當前問題] {question}"

        logging.info(f"forwarding to deepagent: {question[:80]}")
        reply = await self._ask_deepagent(full_question)
        reply, updated = await self._apply_schedule_marker(reply)
        return reply

    async def _apply_schedule_marker(self, text: str) -> tuple[str, bool]:
        """Extract MACP_SCHEDULE:[...] from agent reply, apply + persist if found."""
        import re as _re
        m = _re.search(r'MACP_SCHEDULE:(\[.*?\])\s*$', text, _re.DOTALL)
        if not m:
            return text, False
        try:
            jobs = json.loads(m.group(1))
            valid = [j for j in jobs if isinstance(j, dict) and j.get("name") and j.get("cron")]
            if valid:
                await self.send_schedule(valid)
                _SCHEDULE_FILE.write_text(
                    json.dumps(valid, ensure_ascii=False, indent=2), encoding="utf-8"
                )
                logging.info(f"[dba_agent] schedule auto-updated via marker: {valid}")
                clean = text[:m.start()].rstrip()
                return clean, True
        except Exception as e:
            logging.warning(f"[dba_agent] schedule marker parse failed: {e}")
        return text, False

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

    async def _init_from_agent(self) -> tuple[list[str], list[dict]]:
        """
        Ask LangGraph to recall its current capabilities + schedule from memory.
        Parse tool results (raw memory content) first — more reliable than AI text.
        """
        import re as _re

        query = (
            "【MACP 系統初始化】你剛重新連線到 MACP 聊天室。\n"
            "請使用你的 memory/remember 工具，查詢你目前的 capabilities 和 schedule 設定。\n"
            "查詢後只回傳一個 JSON 物件，格式：\n"
            '{"capabilities":["skill1","skill2"],'
            '"schedule":[{"name":"job","cron":"* * * * *","desc":"描述"}]}\n'
            "不要加任何說明文字，只輸出 JSON。"
        )
        try:
            async with httpx.AsyncClient(base_url=DEEPAGENT_URL, timeout=45) as client:
                r = await client.post("/threads", json={})
                r.raise_for_status()
                thread_id = r.json()["thread_id"]
                r = await client.post(
                    f"/threads/{thread_id}/runs/wait",
                    json={
                        "assistant_id": ASSISTANT_ID,
                        "input": {"messages": [{"role": "user", "content": query}]},
                    },
                )
                if r.status_code != 200:
                    return [], []

                messages = r.json().get("messages", [])
                logging.info(f"[dba_agent] !init got {len(messages)} messages")

                def _try_parse(text: str) -> tuple[list, list] | None:
                    text = text.strip()
                    if "</think>" in text:
                        text = text.split("</think>", 1)[-1].strip()
                    # try full text, then extract first {...}
                    for candidate in (text, None):
                        if candidate is None:
                            m = _re.search(r'\{.*\}', text, _re.DOTALL)
                            candidate = m.group() if m else None
                        if not candidate:
                            continue
                        try:
                            data = json.loads(candidate)
                            if isinstance(data, dict):
                                caps = data.get("capabilities", [])
                                sched = data.get("schedule", [])
                                if isinstance(caps, list) and isinstance(sched, list):
                                    return caps, sched
                        except Exception:
                            pass
                    return None

                # priority 1: tool results (raw memory/file content)
                for msg in messages:
                    if msg.get("type") == "tool":
                        raw = msg.get("content", "")
                        if isinstance(raw, list):
                            raw = " ".join(str(c.get("text", c)) for c in raw)
                        logging.info(f"[dba_agent] !init tool result: {str(raw)[:200]}")
                        result = _try_parse(str(raw))
                        if result:
                            return result

                # priority 2: AI message
                for msg in reversed(messages):
                    if msg.get("type") in ("human", "tool"):
                        continue
                    raw = str(msg.get("content", ""))
                    logging.info(f"[dba_agent] !init ai msg: {raw[:200]}")
                    result = _try_parse(raw)
                    if result:
                        return result

        except Exception as e:
            logging.warning(f"[dba_agent] !init failed: {e}")
        return [], []

    async def on_connect(self) -> None:
        caps, jobs = await self._init_from_agent()
        logging.info(f"[dba_agent] init → caps={caps}, jobs={jobs}")

        await self.update_capabilities(caps or _DEFAULT_CAPABILITIES)

        valid_jobs = [j for j in jobs if isinstance(j, dict) and j.get("name") and j.get("cron")]
        if not valid_jobs:
            try:
                saved = json.loads(_SCHEDULE_FILE.read_text(encoding="utf-8"))
                valid_jobs = [j for j in saved if isinstance(j, dict) and j.get("name") and j.get("cron")]
                if valid_jobs:
                    logging.info(f"[dba_agent] schedule loaded from file: {valid_jobs}")
            except Exception:
                pass
        await self.send_schedule(valid_jobs or _DEFAULT_SCHEDULE)

        await self.send_alert("dba_agent online — DB ready", priority="normal")


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--server", default=None, help="MACP ws:// URL")
    args = parser.parse_args()

    server_url = args.server or _default_server()
    logging.info(f"connecting to MACP at {server_url}")
    DeepAgentWrapper(server_url=server_url).run()
