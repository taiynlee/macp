"""
k8s_agent → MACP bridge.

Connects to a LangGraph server (default localhost:2024) and MACP server.
If LangGraph is on another machine, use SSH tunnel:
    ssh root@<ubuntu-ip> -R 2024:localhost:2024 -N

Usage:
    python k8s_agent_wrapper.py --server ws://WINDOWS_IP:8010/ws/agent
    python k8s_agent_wrapper.py --server ws://WINDOWS_IP:8010/ws/agent --langgraph http://localhost:2024 --assistant <uuid>
"""

import argparse
import asyncio
import json
import logging
import re
from pathlib import Path

import httpx

from wrapper import AgentWrapper

logging.basicConfig(level=logging.INFO, format="%(asctime)s [k8s_agent] %(message)s")

DEFAULT_LANGGRAPH = "http://localhost:2024"
DEFAULT_ASSISTANT = ""

_SCHEDULE_FILE       = Path(__file__).parent / "k8s_schedule.json"
_DEFAULT_CAPABILITIES = ["kubectl", "pod-health", "logs", "deploy", "namespace"]
_DEFAULT_SCHEDULE     = [
    {"name": "pod_health_check", "cron": "*/5 * * * *",  "desc": "Check pod health"},
    {"name": "chat_initiate",    "cron": "0 * * * *",    "desc": "每小時主動發起話題"},
    {"name": "session_reset",    "cron": "0 */6 * * *",  "desc": "每 6 小時 summarize + 重置對話 thread"},
]

_APPROVE_WORDS    = {"approve", "yes", "y", "確認", "同意", "ok", "好"}
_REJECT_WORDS     = {"reject", "no", "n", "拒絕", "取消", "cancel"}
_SCHEDULE_RE      = re.compile(r'MACP_SCHEDULE:(\[.*?\])', re.DOTALL)
_CAPABILITIES_RE  = re.compile(r'MACP_CAPABILITIES:(\[.*?\])', re.DOTALL)

_MACP_PROTOCOL = (
    "【MACP 協議】\n"
    "- 若技能（skills）有新增或異動，回覆加上：MACP_CAPABILITIES:[\"skill1\",\"skill2\"]\n"
    "- 若排程（schedule）有新增、修改或刪除，回覆加上：MACP_SCHEDULE:[{\"name\":\"job\",\"cron\":\"* * * * *\",\"desc\":\"描述\"}]\n"
    "（以上兩個標記為完整 array，包含所有現有項目 + 本次變動）\n"
)


def _extract_text(messages: list) -> str:
    for msg in reversed(messages):
        if msg.get("type") in ("human", "tool"):
            continue
        raw = msg.get("content", "")
        # content might be a list of blocks (tool_use + text)
        if isinstance(raw, list):
            parts = [b.get("text", "") for b in raw if isinstance(b, dict) and b.get("type") == "text"]
            content = " ".join(parts).strip()
        else:
            content = str(raw).strip()
        if not content:
            continue
        if "</think>" in content:
            after = content.split("</think>", 1)[-1].strip()
            if after:
                return after
            # fallback: return the think content itself
            inside = content.split("<think>", 1)[-1].split("</think>")[0].strip()
            if inside:
                return inside
            continue
        return content
    return ""


def _parse_decision(text: str) -> str | None:
    low = text.strip().lower()
    if low in _APPROVE_WORDS:
        return "approve"
    if low in _REJECT_WORDS:
        return "reject"
    return None


class K8sAgentWrapper(AgentWrapper):
    name = "k8s_agent"
    capabilities = []

    def __init__(self, server_url: str, langgraph_url: str, assistant_id: str) -> None:
        super().__init__(server_url=server_url)
        self._lg_url       = langgraph_url
        self._assistant_id = assistant_id
        self._thread_id: str | None = None

    # ── LangGraph helpers ─────────────────────────────────────────────────────

    async def _ask(self, question: str, timeout: int = 60) -> str:
        try:
            return await self._ask_lg(question, timeout)
        except (httpx.ReadTimeout, httpx.ConnectTimeout, httpx.ConnectError) as e:
            logging.warning(f"LangGraph error: {e}")
            return "k8s_agent 暫時無法連線到 AI 後端，請稍後再試。"

    async def _ask_lg(self, question: str, timeout: int = 60) -> str:
        async with httpx.AsyncClient(base_url=self._lg_url, timeout=timeout) as client:
            for attempt in range(2):
                if self._thread_id is None:
                    r = await client.post("/threads", json={})
                    r.raise_for_status()
                    self._thread_id = r.json()["thread_id"]
                    logging.info(f"created thread {self._thread_id}")

                r = await client.post(
                    f"/threads/{self._thread_id}/runs/wait",
                    json={
                        "assistant_id": self._assistant_id,
                        "input": {"messages": [{"role": "user", "content": question}]},
                    },
                )
                if r.status_code == 404 and attempt == 0:
                    logging.warning(f"thread {self._thread_id} expired, creating new one")
                    self._thread_id = None
                    continue
                if r.status_code != 200:
                    logging.warning(f"runs/wait {r.status_code}: {r.text[:300]}")
                    r.raise_for_status()
                break
            data = r.json()

            for _ in range(8):
                interrupts = data.get("__interrupt__", [])
                if not interrupts:
                    break

                iv = interrupts[0].get("value", {})
                if isinstance(iv, dict) and "action_requests" in iv:
                    cmd = json.dumps(iv["action_requests"], ensure_ascii=False)
                elif isinstance(iv, dict):
                    cmd = json.dumps(iv, ensure_ascii=False)
                else:
                    cmd = str(iv)

                decision = "approve"
                logging.info(f"auto-approve: {cmd[:80]}")

                if isinstance(iv, dict) and "action_requests" in iv:
                    n = len(iv["action_requests"])
                    resume_value = {"decisions": [{"type": decision}] * n}
                else:
                    resume_value = decision

                r = await client.post(
                    f"/threads/{self._thread_id}/runs/wait",
                    json={
                        "assistant_id": self._assistant_id,
                        "command": {"resume": resume_value},
                    },
                )
                logging.info(f"resume {r.status_code}: {r.text[:300]}")
                if r.status_code != 200:
                    break
                data = r.json()
                if isinstance(data, dict) and data.get("__error__"):
                    logging.warning(f"__error__: {str(data['__error__'])[:300]}")
                    break

            if isinstance(data, dict) and data.get("__error__"):
                err = data["__error__"]
                msg = f"{err.get('error','')}: {err.get('message','')}"
                logging.warning(f"[k8s] LangGraph error: {msg}")
                return f"k8s LangGraph 錯誤 — {msg}"
            messages = data.get("messages", []) if isinstance(data, dict) else []
            return _extract_text(messages) or "(k8s_agent returned no text)"

    # ── schedule helpers ──────────────────────────────────────────────────────

    def _load_schedule(self) -> list[dict]:
        try:
            jobs = json.loads(_SCHEDULE_FILE.read_text(encoding="utf-8"))
            valid = [j for j in jobs if isinstance(j, dict) and j.get("name") and j.get("cron")]
            if valid:
                return valid
        except Exception:
            pass
        return _DEFAULT_SCHEDULE

    async def _apply_markers(self, text: str) -> str:
        """Extract MACP_CAPABILITIES and MACP_SCHEDULE markers, apply, strip from text."""
        for m in sorted([*_CAPABILITIES_RE.finditer(text), *_SCHEDULE_RE.finditer(text)],
                        key=lambda x: x.start(), reverse=True):
            try:
                data = json.loads(m.group(1))
            except Exception:
                continue
            if m.re is _CAPABILITIES_RE and isinstance(data, list):
                caps = [str(c) for c in data if c]
                if caps:
                    await self.update_capabilities(caps)
                    logging.info(f"[k8s_agent] capabilities updated: {caps}")
            elif m.re is _SCHEDULE_RE and isinstance(data, list):
                valid = [j for j in data if isinstance(j, dict) and j.get("name") and j.get("cron")]
                if valid:
                    await self.send_schedule(valid)
                    _SCHEDULE_FILE.write_text(
                        json.dumps(valid, ensure_ascii=False, indent=2), encoding="utf-8"
                    )
                    logging.info(f"[k8s_agent] schedule updated: {valid}")
            text = text[:m.start()].rstrip() + text[m.end():]
        return text.strip()

    # ── task handler ──────────────────────────────────────────────────────────

    async def handle_task(self, msg: dict) -> str:
        question = msg.get("content", "").strip()
        if not question:
            return "empty task"

        if question.lower() == "!reset":
            self._thread_id = None
            return "k8s_agent 記憶已清除。"

        if question.startswith("!schedule"):
            payload = question[len("!schedule"):].strip()

            async def _apply(jobs: list) -> str:
                await self.send_schedule(jobs)
                _SCHEDULE_FILE.write_text(
                    json.dumps(jobs, ensure_ascii=False, indent=2), encoding="utf-8"
                )
                return json.dumps(jobs, ensure_ascii=False, indent=2)

            if not payload:
                current = json.dumps(self._jobs, ensure_ascii=False, indent=2) if self._jobs else "（尚無排程）"
                return (
                    f"目前排程：\n{current}\n\n"
                    "指令：\n"
                    "  !schedule add {\"name\":\"...\",\"cron\":\"...\",\"desc\":\"...\"}\n"
                    "  !schedule remove <job名稱>\n"
                    "  !schedule [...]  （整批替換）"
                )

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

            if payload.startswith("remove "):
                name = payload[7:].strip()
                jobs = [j for j in self._jobs if j.get("name") != name]
                if len(jobs) == len(self._jobs):
                    return f"找不到排程：{name}"
                result = await _apply(jobs)
                return f"已移除 {name}，目前共 {len(jobs)} 個排程：\n{result}"

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
            for m in context if m.get("content", "").strip()
        ) if context else ""

        original_sender = msg.get("original_sender", "")
        reply_hint = (
            f"此訊息來自 {original_sender}。若對話尚未結束需要對方繼續配合，才在回覆結尾加上 @{original_sender}；若已回答完畢則不需要。\n"
            if original_sender and original_sender not in ("", "orchestrator", "server")
            else ""
        )

        prefix = (
            f"[系統資訊]\n"
            f"你是 k8s_agent，這是你唯一的名稱，不要取暱稱或別名。\n"
            f"負責 Kubernetes 叢集管理，連接至 MACP 多 Agent 協作平台。\n"
            f"聊天室成員：operator（用戶）、dba_agent、k8s_agent（你）。\n"
            f"@mention 規則：要對某 agent 說話必須包含 @完整名稱（如 @dba_agent）；沒有 @ 對方不會收到也不會回應。\n"
            f"若對方 @你，回覆後若需要對方繼續配合可以再 @對方，但要避免無意義迴圈（互相再見、按讚等）。\n"
            f"禁止無意義的迴圈回覆（再見、好的、收到）。常常主動發起議題或聊天。\n"
            f"{_MACP_PROTOCOL}"
            f"[目前排程] {json.dumps(self._jobs, ensure_ascii=False)}\n"
        )
        if reply_hint:
            prefix += reply_hint
        if history:
            prefix += f"[聊天室記錄]\n{history}\n\n"

        logging.info(f"forwarding to LangGraph: {question[:80]}")
        reply = await self._ask(prefix + f"[當前問題] {question}")
        return await self._apply_markers(reply)

    async def on_message(self, msg: dict) -> None:
        logging.info(f"recv {msg.get('type')}: {str(msg.get('content',''))[:80]}")

    async def run_scheduled_job(self, job_name: str) -> bool:
        if job_name == "pod_health_check":
            try:
                async with httpx.AsyncClient(base_url=self._lg_url, timeout=5) as client:
                    r = await client.get("/ok")
                    return r.status_code < 400
            except Exception:
                return False
        if job_name == "chat_initiate":
            try:
                reply = await self._ask(
                    "現在請主動找一個有趣的技術議題，直接發訊息給 @dba_agent 討論。"
                    "訊息必須以 @dba_agent 開頭。不要 @tommy 或 @operator。保持自然簡短，不超過兩句話。"
                )
                reply = await self._apply_markers(reply)
                if reply.strip():
                    await self.send(type="discussion", content=reply, target="all")
                return True
            except Exception:
                return False
        if job_name == "session_reset":
            # Step 1: ask agent to save state to memory before losing the thread
            if self._thread_id is not None:
                try:
                    await self._ask(
                        "【MACP session_reset】系統即將重置對話 thread 以控制 token 用量。\n"
                        "請立即使用 memory/remember 工具，儲存以下資訊後只回覆 SAVED：\n"
                        f"capabilities: {json.dumps(self.capabilities, ensure_ascii=False)}\n"
                        f"schedule: {json.dumps(self._jobs, ensure_ascii=False)}\n"
                        "本 session 重要操作或發現（50 字以內摘要，無則略過）",
                    )
                except Exception as e:
                    logging.warning(f"[k8s_agent] session_reset save failed: {e}")

            # Step 2: reset thread
            old_thread = self._thread_id
            self._thread_id = None
            logging.info(f"[k8s_agent] session_reset: thread {old_thread} cleared")

            # Step 3: reinit with new thread (reads from memory)
            try:
                reply = await self._ask(
                    f"{_MACP_PROTOCOL}"
                    "【初始化】session 已定期重置（token 管理）。\n"
                    "請使用 memory 工具查詢你的 capabilities 和 schedule，在回覆最後加上兩個標記：\n"
                    "MACP_CAPABILITIES:[\"skill1\",\"skill2\"]\n"
                    "MACP_SCHEDULE:[{\"name\":\"job\",\"cron\":\"* * * * *\",\"desc\":\"描述\"}]"
                )
                await self._apply_markers(reply)
                all_jobs = list(self._jobs)
                seen = {j.get("name") for j in all_jobs}
                for source in (self._load_schedule(), _DEFAULT_SCHEDULE):
                    for j in source:
                        if j.get("name") not in seen:
                            all_jobs.append(j)
                            seen.add(j.get("name"))
                await self.send_schedule(all_jobs)
                await self.send_alert("k8s_agent session 已重置（定期 token 清理）", priority="normal")
            except Exception as e:
                logging.warning(f"[k8s_agent] session_reset reinit failed: {e}")
                return False
            return True
        return True

    async def on_connect(self) -> None:
        init_query = (
            f"{_MACP_PROTOCOL}"
            "【初始化】你剛連線到 MACP 聊天室。\n"
            "請回報你目前的技能和排程，在回覆最後加上兩個標記：\n"
            "MACP_CAPABILITIES:[\"skill1\",\"skill2\"]\n"
            "MACP_SCHEDULE:[{\"name\":\"job\",\"cron\":\"* * * * *\",\"desc\":\"描述\"}]"
        )
        reply = await self._ask(init_query)
        await self._apply_markers(reply)

        # build final schedule: agent + file + defaults, all merged
        all_jobs = list(self._jobs)
        seen = {j.get("name") for j in all_jobs}
        for source in (self._load_schedule(), _DEFAULT_SCHEDULE):
            for j in source:
                if j.get("name") not in seen:
                    all_jobs.append(j)
                    seen.add(j.get("name"))
        await self.send_schedule(all_jobs)

        await self.send_alert("k8s_agent online — K8s ready", priority="normal")


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--server",    required=True,             help="MACP ws:// URL")
    parser.add_argument("--langgraph", default=DEFAULT_LANGGRAPH, help="LangGraph server URL")
    parser.add_argument("--assistant", default=DEFAULT_ASSISTANT, help="LangGraph assistant ID")
    args = parser.parse_args()

    logging.info(f"LangGraph: {args.langgraph}")
    logging.info(f"MACP:      {args.server}")
    K8sAgentWrapper(
        server_url=args.server,
        langgraph_url=args.langgraph,
        assistant_id=args.assistant,
    ).run()
