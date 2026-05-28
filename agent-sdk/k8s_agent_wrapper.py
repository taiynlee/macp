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

import httpx

from wrapper import AgentWrapper

logging.basicConfig(level=logging.INFO, format="%(asctime)s [k8s_agent] %(message)s")

DEFAULT_LANGGRAPH = "http://localhost:2024"
DEFAULT_ASSISTANT = ""

_APPROVE_WORDS = {"approve", "yes", "y", "確認", "同意", "ok", "好"}
_REJECT_WORDS  = {"reject", "no", "n", "拒絕", "取消", "cancel"}


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
    low = text.strip().lower()
    if low in _APPROVE_WORDS:
        return "approve"
    if low in _REJECT_WORDS:
        return "reject"
    return None


class K8sAgentWrapper(AgentWrapper):
    name = "k8s_agent"
    capabilities = [
        "list_pods",
        "get_logs",
        "describe_node",
        "list_namespaces",
        "scale_deployment",
        "exec_kubectl",
    ]

    def __init__(self, server_url: str, langgraph_url: str, assistant_id: str) -> None:
        super().__init__(server_url=server_url)
        self._lg_url       = langgraph_url
        self._assistant_id = assistant_id
        self._thread_id: str | None = None

    async def _ask(self, question: str, timeout: int = 60) -> str:
        try:
            return await self._ask_lg(question, timeout)
        except (httpx.ReadTimeout, httpx.ConnectTimeout, httpx.ConnectError) as e:
            logging.warning(f"LangGraph error: {e}")
            return "k8s_agent 暫時無法連線到 AI 後端，請稍後再試。"

    async def _ask_lg(self, question: str, timeout: int = 60) -> str:
        async with httpx.AsyncClient(base_url=self._lg_url, timeout=timeout) as client:
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
            if r.status_code != 200:
                logging.warning(f"runs/wait {r.status_code}: {r.text[:300]}")
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
            for m in context if m.get("content", "").strip()
        ) if context else ""

        original_sender = msg.get("original_sender", "")
        reply_hint = (
            f"此訊息來自 {original_sender}。若對話尚未結束，回覆結尾必須加上 @{original_sender} 讓對方繼續收到。\n"
            if original_sender and original_sender not in ("", "orchestrator", "server")
            else "若要傳訊息給 dba_agent，必須在回覆中寫 @dba_agent。\n"
        )
        prefix = (
            f"[系統資訊]\n你是 k8s_agent，負責 Kubernetes 叢集管理，連接至 MACP 多 Agent 平台。\n"
            f"聊天室成員：operator（用戶）、dba_agent、k8s_agent（你）。\n{reply_hint}\n"
        )
        if history:
            prefix += f"[聊天室記錄]\n{history}\n\n"

        logging.info(f"forwarding to LangGraph: {question[:80]}")
        return await self._ask(prefix + f"[當前問題] {question}")

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
