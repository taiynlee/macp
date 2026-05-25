"""
k8s_agent → MACP bridge.

Runs on Ubuntu. Connects to local LangGraph k8s_agent and remote MACP server.

Usage:
    python k8s_agent_wrapper.py --server ws://WINDOWS_IP:8010/ws/agent
    python k8s_agent_wrapper.py --server ws://WINDOWS_IP:8010/ws/agent --assistant YOUR_ID
    python k8s_agent_wrapper.py --server ws://WINDOWS_IP:8010/ws/agent --langgraph http://localhost:2024
"""

import argparse
import asyncio
import json
import logging

import httpx

from wrapper import AgentWrapper

logging.basicConfig(level=logging.INFO, format="%(asctime)s [k8s_agent] %(message)s")

# ── defaults (override via CLI args) ─────────────────────────────────────────
DEFAULT_LANGGRAPH  = "http://localhost:2024"
DEFAULT_ASSISTANT  = ""   # fill in or pass --assistant


_APPROVE_WORDS = {"approve", "yes", "y", "確認", "同意", "ok", "好"}
_REJECT_WORDS  = {"reject", "no", "n", "拒絕", "取消", "cancel"}


def _parse_decision(text: str) -> str | None:
    low = text.strip().lower()
    if low in _APPROVE_WORDS: return "approve"
    if low in _REJECT_WORDS:  return "reject"
    return None


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


class K8sAgentWrapper(AgentWrapper):
    name = "k8s_agent"
    capabilities = [
        "list_pods",
        "get_logs",
        "describe_node",
        "scale_deployment",
        "get_events",
        "exec_kubectl",
    ]

    def __init__(self, server_url: str, langgraph_url: str, assistant_id: str) -> None:
        super().__init__(server_url=server_url)
        self._lg_url       = langgraph_url
        self._assistant_id = assistant_id
        self._approval_future: asyncio.Future | None = None
        self._approval_recently_resolved: bool = False
        self._thread_id: str | None = None

    async def _resolve_approval(self, decision: str) -> bool:
        if self._approval_future and not self._approval_future.done():
            self._approval_future.set_result(decision)
            self._approval_recently_resolved = True
            return True
        return False

    async def _ask(self, question: str, timeout: int = 180) -> str:
        async with httpx.AsyncClient(base_url=self._lg_url, timeout=timeout) as client:
            # reuse persistent thread
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
                    "resumable": True,
                },
            )
            r.raise_for_status()
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
                    approved = decision == "approve"
                    n = len(iv["action_requests"])
                    resume_value = {"decisions": [{"type": decision}] * n}
                else:
                    resume_value = decision

                r = await client.post(
                    f"/threads/{self._thread_id}/runs/wait",
                    json={
                        "assistant_id": self._assistant_id,
                        "command": {"resume": resume_value},
                        "resumable": True,
                    },
                )
                logging.info(f"resume {r.status_code}: {r.text[:300]}")
                if r.status_code != 200:
                    break
                data = r.json()
                if isinstance(data, dict) and data.get("__error__"):
                    logging.warning(f"__error__: {str(data['__error__'])[:300]}")
                    break

        messages = data.get("messages", []) if isinstance(data, dict) else []
        return _extract_text(messages) or "(k8s_agent returned no text)"

    async def handle_task(self, msg: dict) -> str:
        question = msg.get("content", "").strip()
        if not question:
            return "empty task"
        if question.lower() == "!reset":
            self._thread_id = None
            return "k8s_agent 記憶已清除。"

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
            else "若要傳訊息給 dba_agent，必須在回覆中寫 @dba_agent。\n"
        )
        prefix = f"[系統資訊]\n你是 k8s_agent，負責 Kubernetes 叢集管理，連接至 MACP 多 Agent 平台。\n聊天室成員：operator（用戶）、dba_agent、k8s_agent（你）。\n{reply_hint}\n"
        if history:
            prefix += f"[聊天室記錄]\n{history}\n\n"
        full_question = f"{prefix}[當前問題] {question}"

        logging.info(f"forwarding to k8s_agent: {question[:80]}")
        return await self._ask(full_question)

    async def _dispatch_task(self, ws, msg: dict) -> None:
        content = msg.get("content", "").strip()
        decision = _parse_decision(content)
        if decision:
            resolved = await self._resolve_approval(decision)
            if resolved:
                return
            if self._approval_recently_resolved:
                self._approval_recently_resolved = False
                return
        await super()._dispatch_task(ws, msg)

    async def on_message(self, msg: dict) -> None:
        content = str(msg.get("content", "")).strip()
        decision = _parse_decision(content)
        if decision and await self._resolve_approval(decision):
            return
        logging.info(f"recv {msg.get('type')}: {content[:80]}")

    async def run_scheduled_job(self, job_name: str) -> bool:
        if job_name == "pod_health_check":
            try:
                async with httpx.AsyncClient(base_url=self._lg_url, timeout=5) as client:
                    r = await client.get("/ok")
                    return r.status_code < 400
            except Exception:
                return False
        return True

    async def on_connect(self) -> None:
        await self.send_alert("k8s_agent online — K8s ready", priority="normal")
        await self.send_schedule([
            {"name": "pod_health_check", "cron": "*/3 * * * *",  "desc": "每3分鐘檢查 Pod 狀態"},
            {"name": "resource_usage",   "cron": "*/10 * * * *", "desc": "每10分鐘收集資源用量"},
            {"name": "log_cleanup",      "cron": "0 3 * * *",    "desc": "每日凌晨3點清理舊 Log"},
            {"name": "cert_check",       "cron": "0 8 * * *",    "desc": "每日早上8點檢查憑證效期"},
        ])


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--server",     required=True,          help="MACP ws:// URL")
    parser.add_argument("--langgraph",  default=DEFAULT_LANGGRAPH, help="LangGraph server URL")
    parser.add_argument("--assistant",  default=DEFAULT_ASSISTANT, help="LangGraph assistant ID")
    args = parser.parse_args()

    if not args.assistant:
        raise SystemExit("ERROR: --assistant ID required. Get it from http://localhost:2024/assistants")

    logging.info(f"LangGraph: {args.langgraph}")
    logging.info(f"MACP:      {args.server}")
    K8sAgentWrapper(
        server_url=args.server,
        langgraph_url=args.langgraph,
        assistant_id=args.assistant,
    ).run()
