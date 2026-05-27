import json
import uuid
from collections import deque
from datetime import datetime, timezone

from fastapi import APIRouter, WebSocket, WebSocketDisconnect

from ..core.orchestrator import orchestrator
from ..core.registry import AgentInfo, registry

router = APIRouter()

_chat_context: deque[dict] = deque(maxlen=15)


def _store_context(sender: str, msg: dict) -> None:
    content = msg.get("content", "").strip()
    if content and msg.get("type") not in ("system",):
        _chat_context.append({
            "sender": sender,
            "content": content,
            "type": msg.get("type", "discussion"),
        })


class ConnectionManager:
    def __init__(self) -> None:
        self._connections: dict[str, WebSocket] = {}

    async def connect(self, identity: str, ws: WebSocket) -> None:
        await ws.accept()
        self._connections[identity] = ws

    def disconnect(self, identity: str) -> None:
        self._connections.pop(identity, None)

    async def broadcast(self, message: str) -> None:
        dead: list[str] = []
        for identity, ws in self._connections.items():
            try:
                await ws.send_text(message)
            except Exception:
                dead.append(identity)
        for identity in dead:
            self._connections.pop(identity, None)


manager = ConnectionManager()


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _envelope(sender: str, msg: dict) -> str:
    msg.setdefault("id", str(uuid.uuid4()))
    msg.setdefault("timestamp", _now())
    msg.setdefault("sender", sender)
    return json.dumps(msg)


# ── UI user endpoint ──────────────────────────────────────────────────────────

@router.websocket("/ws")
async def user_ws(ws: WebSocket, name: str = "user") -> None:
    identity = f"user:{name}"
    await manager.connect(identity, ws)
    try:
        while True:
            raw = await ws.receive_text()
            try:
                msg = json.loads(raw)
            except json.JSONDecodeError:
                await ws.send_text(json.dumps({"error": "invalid JSON"}))
                continue

            await manager.broadcast(_envelope(name, msg))
            _store_context(name, msg)

            if msg.get("type") == "discussion" and msg.get("content", "").strip():
                ctx = list(_chat_context)
                agent_name = await orchestrator.route(msg)
                if agent_name:
                    await orchestrator.dispatch(agent_name, msg, context=ctx)
                else:
                    # no specific match → broadcast task to all online agents
                    for agent in registry.list_agents():
                        await orchestrator.dispatch(agent["name"], msg, context=ctx)

    except WebSocketDisconnect:
        manager.disconnect(identity)


# ── Agent endpoint ────────────────────────────────────────────────────────────

@router.websocket("/ws/agent")
async def agent_ws(ws: WebSocket, name: str) -> None:
    if not name:
        await ws.close(code=1008)
        return

    identity = f"agent:{name}"
    await manager.connect(identity, ws)

    try:
        while True:
            raw = await ws.receive_text()
            try:
                msg = json.loads(raw)
            except json.JSONDecodeError:
                await ws.send_text(json.dumps({"error": "invalid JSON"}))
                continue

            msg_type = msg.get("type")
            action = msg.get("action")

            if msg_type == "system" and action == "register":
                registry.register(AgentInfo(
                    name=name,
                    capabilities=msg.get("capabilities", []),
                    ws=ws,
                ))
                # send ack first so wrapper sees "registered"
                await ws.send_text(json.dumps({
                    "type": "system",
                    "action": "registered",
                    "name": name,
                    "timestamp": _now(),
                }))
                # broadcast after registry is populated so frontend GET /agents works
                await manager.broadcast(json.dumps({
                    "id": str(uuid.uuid4()),
                    "timestamp": _now(),
                    "sender": "server",
                    "type": "system",
                    "action": "agent_connected",
                    "name": name,
                }))
                continue

            if msg_type == "system" and action == "heartbeat":
                registry.heartbeat(name)
                continue

            if msg_type == "system" and action == "set_schedule":
                registry.set_schedule(name, msg.get("jobs", []))
                continue

            if msg_type == "system" and action == "job_result":
                registry.report_job(name, msg.get("job", ""), msg.get("success", False))
                await manager.broadcast(json.dumps({
                    "type": "system",
                    "action": "schedule_updated",
                    "name": name,
                }))
                continue

            _store_context(name, msg)
            await manager.broadcast(_envelope(name, msg))

            # agent-to-agent: if report/discussion mentions another agent, dispatch to it
            if msg.get("type") in ("report", "discussion"):
                content = msg.get("content", "")
                ctx = list(_chat_context)
                for a in registry.list_agents():
                    if a["name"] != name and f"@{a['name']}" in content:
                        await orchestrator.dispatch(a["name"], {
                            "content": content,
                            "sender": name,
                        }, context=ctx)
                        break

    except WebSocketDisconnect:
        registry.unregister(name)
        manager.disconnect(identity)
        await manager.broadcast(json.dumps({
            "id": str(uuid.uuid4()),
            "timestamp": _now(),
            "sender": "server",
            "type": "system",
            "action": "agent_disconnected",
            "name": name,
        }))
