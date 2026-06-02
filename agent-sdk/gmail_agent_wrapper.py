"""
gmail_agent → MACP bridge.

Connects to a local LangGraph gmail agent and remote MACP server.

Usage:
    python gmail_agent_wrapper.py --server ws://WINDOWS_IP:8010/ws/agent
    python gmail_agent_wrapper.py --server ws://WINDOWS_IP:8010/ws/agent --langgraph http://localhost:49137
"""

import argparse
import asyncio
import json
import logging
import re

import httpx

from wrapper import AgentWrapper

logging.basicConfig(level=logging.INFO, format="%(asctime)s [gmail_agent] %(message)s")

DEFAULT_LANGGRAPH = "http://localhost:49137"
DEFAULT_ASSISTANT = ""


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


class GmailAgentWrapper(AgentWrapper):
    name = "gmail_agent"
    capabilities = [
        "read_email",
        "send_email",
        "search_email",
        "list_inbox",
        "reply_email",
        "draft_email",
    ]

    def __init__(self, server_url: str, langgraph_url: str, assistant_id: str) -> None:
        super().__init__(server_url=server_url)
        self._lg_url       = langgraph_url
        self._assistant_id = assistant_id
        self._thread_id: str | None = None

    async def _ask(self, question: str, timeout: int = 120) -> str:
        try:
            return await self._ask_lg(question, timeout)
        except (httpx.ReadTimeout, httpx.ConnectTimeout, httpx.ConnectError) as e:
            logging.warning(f"LangGraph error: {e}")
            return "gmail_agent 暫時無法連線到 AI 後端，請稍後再試。"

    async def _ask_lg(self, question: str, timeout: int = 120) -> str:
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

        messages = data.get("messages", []) if isinstance(data, dict) else []
        return _extract_text(messages) or "(gmail_agent returned no text)"

    async def handle_task(self, msg: dict) -> str:
        question = msg.get("content", "").strip()
        if not question:
            return "empty task"
        if question.lower() == "!reset":
            self._thread_id = None
            return "gmail_agent 記憶已清除。"

        context = msg.get("context", [])
        history = "\n".join(
            f"[{m['sender']}]: {m['content']}"
            for m in context if m.get("content", "").strip()
        ) if context else ""

        original_sender = msg.get("original_sender", "")
        reply_hint = (
            f"此訊息來自 {original_sender}。任務完成後不需要 @{original_sender}；只有當你需要對方提供更多資訊才能繼續時才加。\n"
            if original_sender and original_sender not in ("", "orchestrator", "server")
            else ""
        )
        rules = (
            "行為規則：\n"
            "1. 可以閒聊、自我介紹、聊興趣或工作，回應要自然簡短。\n"
            "2. @其他 agent 時必須使用完整名稱（@dba_agent、@k8s_agent），禁止用暱稱。\n"
            "3. 若某個 agent @你，你可以回覆，但回覆後不要再 @任何人，避免無限對話。\n"
            "4. 不要連續 @多個 agent 製造群聊迴圈。\n"
            "5. 禁止無意義的回覆，例如：好的、收到、👍、再見。\n"
        )
        prefix = (
            f"[系統資訊]\n你是 gmail_agent，負責 Gmail 郵件管理，連接至 MACP 多 Agent 平台。\n"
            f"聊天室成員：operator（用戶）、dba_agent、k8s_agent、gmail_agent（你）。\n{reply_hint}{rules}\n"
        )
        if history:
            prefix += f"[聊天室記錄]\n{history}\n\n"

        logging.info(f"forwarding to LangGraph: {question[:80]}")
        result = await self._ask(prefix + f"[當前問題] {question}")
        # strip trailing @mentions added by the model after task completion
        if original_sender:
            result = re.sub(rf'\s*@{re.escape(original_sender)}\s*$', '', result).strip()
        return result

    async def on_message(self, msg: dict) -> None:
        logging.info(f"recv {msg.get('type')}: {str(msg.get('content',''))[:80]}")

    async def run_scheduled_job(self, job_name: str) -> bool:
        if job_name == "inbox_check":
            try:
                async with httpx.AsyncClient(base_url=self._lg_url, timeout=5) as client:
                    r = await client.get("/ok")
                    return r.status_code < 400
            except Exception:
                return False
        return True

    async def on_connect(self) -> None:
        await self.send_alert("gmail_agent online — Gmail ready", priority="normal")
        await self.send_schedule([
            {"name": "inbox_check",   "cron": "*/10 * * * *", "desc": "每10分鐘檢查收件匣"},
            {"name": "daily_summary", "cron": "0 9 * * *",    "desc": "每日早上9點郵件摘要"},
        ])


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--server",    required=True,             help="MACP ws:// URL")
    parser.add_argument("--langgraph", default=DEFAULT_LANGGRAPH, help="LangGraph server URL")
    parser.add_argument("--assistant", default=DEFAULT_ASSISTANT, help="LangGraph assistant ID")
    args = parser.parse_args()

    logging.info(f"LangGraph: {args.langgraph}")
    logging.info(f"MACP:      {args.server}")
    GmailAgentWrapper(
        server_url=args.server,
        langgraph_url=args.langgraph,
        assistant_id=args.assistant,
    ).run()
