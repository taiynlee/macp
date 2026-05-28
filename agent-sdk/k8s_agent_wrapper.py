"""
k8s_agent → MACP bridge (no LangGraph).

Uses kubernetes Python client directly + Claude for reasoning.
Requires: pip install kubernetes anthropic websockets

Usage:
    python k8s_agent_wrapper.py --server ws://WINDOWS_IP:8010/ws/agent
"""

import argparse
import logging
import os
import subprocess

import anthropic
from kubernetes import client, config

from wrapper import AgentWrapper

logging.basicConfig(level=logging.INFO, format="%(asctime)s [k8s_agent] %(message)s")

ANTHROPIC_API_KEY = os.environ.get("ANTHROPIC_API_KEY", "")

try:
    config.load_kube_config()
    _K8S_READY = True
except Exception as e:
    logging.warning(f"k8s config not loaded: {e}")
    _K8S_READY = False


# ── k8s tool implementations ──────────────────────────────────────────────────

def _list_pods(namespace: str = "default") -> str:
    v1 = client.CoreV1Api()
    if namespace == "all":
        pods = v1.list_pod_for_all_namespaces()
        lines = [f"找到 {len(pods.items)} 個 Pods (all namespaces)\n"]
        for pod in pods.items:
            s = "✅" if pod.status.phase == "Running" else "⚠️"
            lines.append(f"{s} {pod.metadata.namespace}/{pod.metadata.name} | {pod.status.phase}")
    else:
        pods = v1.list_namespaced_pod(namespace=namespace)
        lines = [f"找到 {len(pods.items)} 個 Pods (namespace: {namespace})\n"]
        for pod in pods.items:
            s = "✅" if pod.status.phase == "Running" else "⚠️"
            lines.append(f"{s} {pod.metadata.name} | {pod.status.phase}")
    return "\n".join(lines)


def _list_nodes() -> str:
    v1 = client.CoreV1Api()
    nodes = v1.list_node()
    lines = [f"找到 {len(nodes.items)} 個 Nodes\n"]
    for node in nodes.items:
        ready = next((c.status for c in node.status.conditions if c.type == "Ready"), "Unknown")
        s = "✅" if ready == "True" else "❌"
        lines.append(f"{s} {node.metadata.name} | Ready={ready}")
    return "\n".join(lines)


def _describe_node(node_name: str) -> str:
    v1 = client.CoreV1Api()
    node = v1.read_node(name=node_name)
    lines = [f"Node: {node_name}", "=" * 50]
    lines.append("Conditions:")
    for c in node.status.conditions:
        s = "✅" if c.status == "True" else "❌"
        lines.append(f"  {s} {c.type}: {c.reason}")
    lines.append("\nAllocatable:")
    for k, v in node.status.allocatable.items():
        lines.append(f"  {k}: {v}")
    lines.append(f"\nOS: {node.status.node_info.operating_system}")
    lines.append(f"Kubelet: {node.status.node_info.kubelet_version}")
    return "\n".join(lines)


def _list_namespaces() -> str:
    v1 = client.CoreV1Api()
    ns_list = v1.list_namespace()
    lines = [f"找到 {len(ns_list.items)} 個 Namespaces\n"]
    for ns in ns_list.items:
        lines.append(f"• {ns.metadata.name} | {ns.status.phase}")
    return "\n".join(lines)


def _get_pod_logs(pod_name: str, namespace: str = "default", tail_lines: int = 50) -> str:
    v1 = client.CoreV1Api()
    logs = v1.read_namespaced_pod_log(name=pod_name, namespace=namespace, tail_lines=tail_lines)
    return f"[{namespace}/{pod_name} logs]\n{logs}"


def _kubectl(command: str) -> str:
    parts = command.strip().split()
    if parts and parts[0] == "kubectl":
        parts = parts[1:]
    result = subprocess.run(["kubectl"] + parts, capture_output=True, text=True, timeout=30)
    return (result.stdout or result.stderr)[:3000]


def _call_tool(name: str, inputs: dict) -> str:
    try:
        if name == "list_pods":
            return _list_pods(inputs.get("namespace", "default"))
        if name == "list_nodes":
            return _list_nodes()
        if name == "describe_node":
            return _describe_node(inputs["node_name"])
        if name == "list_namespaces":
            return _list_namespaces()
        if name == "get_pod_logs":
            return _get_pod_logs(inputs["pod_name"], inputs.get("namespace", "default"), inputs.get("tail_lines", 50))
        if name == "kubectl":
            return _kubectl(inputs["command"])
        return f"unknown tool: {name}"
    except Exception as e:
        return f"tool error ({name}): {e}"


_TOOLS = [
    {
        "name": "list_pods",
        "description": "List pods. Use namespace='all' for all namespaces.",
        "input_schema": {
            "type": "object",
            "properties": {
                "namespace": {"type": "string", "description": "namespace name or 'all'"}
            },
        },
    },
    {
        "name": "list_nodes",
        "description": "List all nodes in the cluster with Ready status.",
        "input_schema": {"type": "object", "properties": {}},
    },
    {
        "name": "describe_node",
        "description": "Describe a specific node (conditions, resources, OS info).",
        "input_schema": {
            "type": "object",
            "properties": {"node_name": {"type": "string"}},
            "required": ["node_name"],
        },
    },
    {
        "name": "list_namespaces",
        "description": "List all Kubernetes namespaces.",
        "input_schema": {"type": "object", "properties": {}},
    },
    {
        "name": "get_pod_logs",
        "description": "Get recent logs from a pod.",
        "input_schema": {
            "type": "object",
            "properties": {
                "pod_name": {"type": "string"},
                "namespace": {"type": "string"},
                "tail_lines": {"type": "integer"},
            },
            "required": ["pod_name"],
        },
    },
    {
        "name": "kubectl",
        "description": "Run any kubectl command, e.g. 'get pods -A' or 'describe pod my-pod'.",
        "input_schema": {
            "type": "object",
            "properties": {
                "command": {"type": "string", "description": "kubectl args without the 'kubectl' prefix"}
            },
            "required": ["command"],
        },
    },
]


# ── agent ─────────────────────────────────────────────────────────────────────

class K8sAgentWrapper(AgentWrapper):
    name = "k8s_agent"
    capabilities = [
        "list_pods", "get_logs", "describe_node",
        "list_namespaces", "scale_deployment", "exec_kubectl",
    ]

    def __init__(self, server_url: str) -> None:
        super().__init__(server_url=server_url)
        if ANTHROPIC_API_KEY:
            self._claude = anthropic.AsyncAnthropic(api_key=ANTHROPIC_API_KEY)
        else:
            self._claude = None
            logging.warning("ANTHROPIC_API_KEY not set — using keyword fallback")

    async def _ask(self, question: str, raw: str = "") -> str:
        if not self._claude:
            return self._keyword_fallback(raw or question)

        messages = [{"role": "user", "content": question}]
        system = (
            "你是 k8s_agent，Kubernetes 叢集管理專家。"
            "用繁體中文回答。需要查詢叢集狀態時，使用提供的工具。"
        )

        for _ in range(8):
            resp = await self._claude.messages.create(
                model="claude-haiku-4-5-20251001",
                max_tokens=1024,
                system=system,
                tools=_TOOLS,
                messages=messages,
            )

            if resp.stop_reason == "end_turn":
                return next((b.text for b in resp.content if hasattr(b, "text")), "(no response)")

            if resp.stop_reason == "tool_use":
                messages.append({"role": "assistant", "content": resp.content})
                tool_results = []
                for block in resp.content:
                    if block.type == "tool_use":
                        result = _call_tool(block.name, block.input)
                        logging.info(f"tool {block.name}: {result[:80]}")
                        tool_results.append({
                            "type": "tool_result",
                            "tool_use_id": block.id,
                            "content": result,
                        })
                messages.append({"role": "user", "content": tool_results})
            else:
                break

        return "(k8s_agent 無法完成請求)"

    def _keyword_fallback(self, question: str) -> str:
        q = question.lower()
        k8s_keywords = {"pod", "node", "namespace", "kubectl", "deploy", "service",
                        "log", "cluster", "k8s", "kubernetes", "pv", "pvc", "ingress"}
        if not any(kw in q for kw in k8s_keywords):
            return "嗨！我是 k8s_agent，負責 Kubernetes 叢集管理。你可以問我 pod 狀態、node 資訊、namespace 列表等。"
        try:
            if "pod" in q:
                return _list_pods("all")
            if "node" in q:
                return _list_nodes()
            if "namespace" in q or " ns " in q:
                return _list_namespaces()
            if "log" in q:
                return "請指定 pod 名稱，例如：「查看 pod my-pod 的 log」"
            return _list_nodes() + "\n\n" + _list_pods("all")
        except Exception as e:
            return f"k8s error: {e}"

    async def handle_task(self, msg: dict) -> str:
        question = msg.get("content", "").strip()
        if not question:
            return "empty task"
        if question.lower() == "!reset":
            return "k8s_agent 已重置。"

        context = msg.get("context", [])
        history = "\n".join(
            f"[{m['sender']}]: {m['content']}"
            for m in context if m.get("content", "").strip()
        ) if context else ""

        original_sender = msg.get("original_sender", "")
        reply_hint = (
            f"此訊息來自 {original_sender}。若對話尚未結束，回覆結尾必須加上 @{original_sender}。\n"
            if original_sender and original_sender not in ("", "orchestrator", "server")
            else "若要傳訊息給 dba_agent，必須在回覆中寫 @dba_agent。\n"
        )
        prefix = (
            f"[系統資訊]\n你是 k8s_agent，負責 Kubernetes 叢集管理。\n"
            f"聊天室成員：operator（用戶）、dba_agent、k8s_agent（你）。\n{reply_hint}\n"
        )
        if history:
            prefix += f"[聊天室記錄]\n{history}\n\n"

        logging.info(f"processing: {question[:80]}")
        return await self._ask(prefix + f"[當前問題] {question}", raw=question)

    async def on_message(self, msg: dict) -> None:
        logging.info(f"recv {msg.get('type')}: {str(msg.get('content',''))[:80]}")

    async def run_scheduled_job(self, job_name: str) -> bool:
        if job_name == "pod_health_check":
            try:
                result = _list_nodes()
                return "❌" not in result
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
    parser.add_argument("--server", required=True, help="MACP ws:// URL")
    args = parser.parse_args()
    logging.info(f"MACP: {args.server}")
    K8sAgentWrapper(server_url=args.server).run()
