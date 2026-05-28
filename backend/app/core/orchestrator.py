"""
Orchestrator — routes user messages to appropriate agents.

Routing priority:
  1. Explicit target in message (target != "all" / "orchestrator")
  2. Keyword pattern match
  3. LLM intent detection (Claude API, only if ANTHROPIC_API_KEY set)
  4. No match → message is broadcast as-is (discussion)
"""

import json
import logging
import re
import uuid
from datetime import datetime, timezone

import anthropic

from .config import settings
from .registry import registry

logger = logging.getLogger(__name__)

# (compiled_pattern, agent_name)
def _kw(*terms: str, chinese: str = "") -> re.Pattern:
    """Build a keyword pattern that works for both pure-English and Chinese-adjacent text.
    Uses (?<![A-Za-z0-9])..(?![A-Za-z0-9]) instead of \\b so ASCII terms adjacent to
    Chinese characters (e.g. 'db裡面') are still matched correctly."""
    eng = "|".join(terms)
    pattern = rf"(?<![A-Za-z0-9])({eng})(?![A-Za-z0-9])"
    if chinese:
        pattern += "|" + chinese
    return re.compile(pattern, re.I)


KEYWORD_RULES: list[tuple[re.Pattern, str]] = [
    (_kw("db", "database", "postgres", "sql", "connection", "query", "migration", "table", "schema", "dba",
         chinese="資料庫|資料表|查詢|連線|欄位|紀錄"), "dba_agent"),
    (_kw("k8s", "kubernetes", "pod", "pods", "deploy", "deployment", "namespace", "ns",
         "helm", "kubectl", "cluster", "node", "ingress", "svc", "pvc", "hpa", "crd",
         chinese="容器|叢集|部署|服務|命名空間"), "k8s_agent"),
    (_kw("network", "ping", "traceroute", "bandwidth", "dns", "latency", "firewall",
         chinese="網路|防火牆|頻寬|延遲"), "network_agent"),
    (_kw("code", "review", "commit", "git", "branch", "diff", "merge",
         chinese="程式|代碼|提交"), "claude_dev_agent"),
    (_kw("email", "gmail", "mail", "inbox", "draft", "attachment",
         chinese="郵件|信箱|收件|寄信|回信|草稿|附件"), "gmail_agent"),
]

_ROUTE_SYSTEM = """You are a task router for a multi-agent platform.
Given a user message and a list of available agents with their capabilities,
respond with ONLY the agent name that should handle this task.
If no agent fits, respond with exactly: none
Do not explain. One word only."""


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _task_envelope(sender: str, target: str, original_msg: dict, context: list | None = None) -> str:
    return json.dumps({
        "id": str(uuid.uuid4()),
        "timestamp": _now(),
        "sender": sender,
        "target": target,
        "type": "task",
        "content": original_msg.get("content", ""),
        "priority": original_msg.get("priority", "normal"),
        "original_id": original_msg.get("id"),
        "original_sender": original_msg.get("sender", ""),
        "context": context or [],
    })


class Orchestrator:
    def __init__(self) -> None:
        self._client: anthropic.AsyncAnthropic | None = (
            anthropic.AsyncAnthropic(api_key=settings.ANTHROPIC_API_KEY)
            if settings.ANTHROPIC_API_KEY
            else None
        )

    async def route(self, user_msg: dict) -> str | None:
        """
        Decide which agent (if any) should handle this message.
        Returns agent name if routed, None if broadcast as-is.
        Caller is responsible for publishing the task message.
        """
        content = user_msg.get("content", "").strip()
        if not content:
            return None

        # 1. explicit target already set by user
        target = user_msg.get("target", "all")
        if target not in ("all", "orchestrator"):
            if registry.get(target):
                return target

        # 2. keyword match
        agent = self._keyword_route(content)
        if agent:
            logger.info(f"[orchestrator] keyword → {agent}")
            return agent

        # 3. LLM route
        if self._client:
            agent = await self._llm_route(content)
            if agent:
                logger.info(f"[orchestrator] LLM → {agent}")
                return agent

        return None

    async def dispatch(self, agent_name: str, user_msg: dict, context: list | None = None) -> None:
        """Send task directly to agent WebSocket."""
        agent = registry.get(agent_name)
        if not agent:
            logger.warning(f"[orchestrator] agent {agent_name!r} not online, drop task")
            return
        payload = _task_envelope("orchestrator", agent_name, user_msg, context)
        await agent.ws.send_text(payload)

    # ── private ───────────────────────────────────────────────────────────────

    def _keyword_route(self, content: str) -> str | None:
        for pattern, agent_name in KEYWORD_RULES:
            if pattern.search(content) and registry.get(agent_name):
                return agent_name
        return None

    async def _llm_route(self, content: str) -> str | None:
        agents = registry.list_agents()
        if not agents:
            return None

        agent_list = "\n".join(
            f"- {a['name']}: {', '.join(a['capabilities'])}"
            for a in agents
        )
        user_prompt = f"Available agents:\n{agent_list}\n\nUser message: {content}"

        try:
            resp = await self._client.messages.create(
                model="claude-haiku-4-5-20251001",
                max_tokens=16,
                system=_ROUTE_SYSTEM,
                messages=[{"role": "user", "content": user_prompt}],
            )
            name = resp.content[0].text.strip().lower()
            if name == "none":
                return None
            if registry.get(name):
                return name
            logger.warning(f"[orchestrator] LLM returned unknown agent: {name!r}")
        except Exception as exc:
            logger.warning(f"[orchestrator] LLM route failed: {exc}")

        return None


orchestrator = Orchestrator()
