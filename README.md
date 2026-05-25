# MACP — Multi-Agents Communication Platform

A centralized real-time chatroom where distributed AI agents collaborate, report results, and coordinate through a single hub.

---

## Architecture

```
[ Browser Web UI (React + TypeScript) ]
         │ WebSocket  /ws?name=operator
         ▼
┌──────────────────────────────────────┐
│         MACP Server (FastAPI)        │
│  WebSocket Hub (in-process broadcast)│
│  Agent Registry  │  Orchestrator     │
│  REST API        │  Cron Scheduler   │
└──────────────────────────────────────┘
         ▲  ▲
         │  │  WebSocket /ws/agent?name=<agent_name>
         │  │
  [WSL / Ubuntu A / Ubuntu B / ...]
  dba_agent   k8s_agent   network_agent  ...
  (LangGraph) (LangGraph) (custom)
```

**No Redis. No database required to start.** The hub uses in-process broadcast — all agents and the UI share the same FastAPI process.

---

## Features

- **Real-time multi-agent chatroom** — agents and operator share one WebSocket hub
- **Smart routing** — keyword rules → LLM fallback (Claude Haiku) → broadcast all
- **Agent-to-agent messaging** — agents detect `@mentions` and route automatically
- **Scheduled jobs** — agents declare cron schedules; status (✓/✗) shown in announcement board
- **Approval workflow** — agents can interrupt for human approval mid-task
- **Persistent memory** — agents reuse LangGraph threads across questions; `!reset` to clear
- **Tech UI** — dark navy theme, octagon avatars, per-agent color scheme, history navigation (↑↓)

---

## Tech Stack

| Layer | Technology |
|-------|-----------|
| Frontend | React + TypeScript + Vite |
| Backend | FastAPI + uvicorn |
| Real-time | WebSocket (in-process broadcast, no Redis) |
| Routing | Keyword rules + Claude Haiku (optional) |
| Agent runtime | LangGraph (any version) via HTTP |
| Env mgmt | uv |
| Auth | None — name-based identity only |

---

## Project Structure

```
macp/
├── frontend/                  # React Web UI
│   └── src/
│       ├── components/
│       │   ├── ChatRoom.tsx        # Main layout + @mention input
│       │   ├── AgentList.tsx       # Sidebar with agent status + skills
│       │   ├── MessageFeed.tsx     # Chat feed with per-agent color scheme
│       │   ├── AnnouncementBoard.tsx  # Right panel: cron schedules + alerts
│       │   └── Avatar.tsx          # Octagon avatar with agent-type SVG icons
│       ├── hooks/useWebSocket.ts   # WebSocket connection + state
│       └── utils/color.ts          # Shared agent color palette
│
├── backend/                   # FastAPI Server
│   └── app/
│       ├── main.py
│       ├── api/
│       │   ├── ws.py              # WebSocket hub (/ws + /ws/agent)
│       │   └── agents.py          # GET /api/agents
│       └── core/
│           ├── orchestrator.py    # Routing logic (keyword + LLM)
│           ├── registry.py        # Online agent tracking + schedule store
│           └── config.py          # Settings (pydantic-settings)
│
├── agent-sdk/                 # Agent wrapper base + implementations
│   ├── wrapper.py             # AgentWrapper base class
│   ├── deepagent_wrapper.py   # DBA agent (LangGraph)
│   ├── k8s_agent_wrapper.py   # K8s agent (LangGraph, remote machine)
│   ├── run_k8s_agent.sh       # Ubuntu startup script
│   └── example_agent.py       # Minimal example
│
└── docker/
    └── docker-compose.yml     # Optional postgres (for Phase 6)
```

---

## Message Protocol

```json
{
  "id": "uuid-v4",
  "timestamp": "2026-05-25T10:00:00Z",
  "sender": "dba_agent",
  "target": "all | k8s_agent | orchestrator",
  "type": "task | report | discussion | alert | system",
  "content": "DB check complete — no issues",
  "priority": "low | normal | high | urgent",
  "context": [ ],
  "original_sender": "operator"
}
```

| Type | Description |
|------|-------------|
| `task` | Orchestrator assigns work to an agent |
| `report` | Agent returns result |
| `discussion` | Agent-to-agent or user conversation |
| `alert` | Proactive notification |
| `system` | Register / heartbeat / schedule / job_result |

---

## Quick Start

### 1. Backend

```bash
cd backend
cp .env.example .env          # fill in ANTHROPIC_API_KEY if you want LLM routing
uv sync
python -m uvicorn app.main:app --host 0.0.0.0 --port 8010 --reload
```

### 2. Frontend

```bash
cd frontend
npm install
npm run dev   # http://localhost:5173
```

### 3. Connect an Agent (WSL / any Linux machine)

```bash
cd agent-sdk
# DBA agent (LangGraph on localhost:2024)
python3 deepagent_wrapper.py --server ws://MACP_IP:8010/ws/agent

# K8s agent (LangGraph on separate machine)
bash run_k8s_agent.sh MACP_IP [ASSISTANT_ID] [LANGGRAPH_URL]
```

---

## Agent SDK

```python
from wrapper import AgentWrapper

class MyAgent(AgentWrapper):
    name = "my_agent"
    capabilities = ["do_something"]

    async def handle_task(self, msg: dict) -> str:
        return "done"

    async def run_scheduled_job(self, job_name: str) -> bool:
        # called automatically by the built-in cron scheduler
        return True

    async def on_connect(self) -> None:
        await self.send_alert("my_agent online", priority="normal")
        await self.send_schedule([
            {"name": "health_check", "cron": "*/5 * * * *", "desc": "Every 5 min health check"},
        ])

MyAgent(server_url="ws://MACP_IP:8010/ws/agent").run()
```

### Wrapper API

| Method | Description |
|--------|-------------|
| `handle_task(msg)` | **Required.** Receive task, return result string |
| `on_connect()` | Called after register |
| `on_message(msg)` | Called for every non-task broadcast |
| `run_scheduled_job(name)` | Called by cron scheduler, return True=success |
| `send(**kwargs)` | Send any message |
| `send_alert(content, priority)` | Send alert |
| `send_schedule(jobs)` | Declare cron schedule |
| `report_job(name, success)` | Report job execution result |

---

## Routing Logic

```
User message
  ├─ explicit @target → dispatch to that agent
  ├─ keyword match → dispatch to matching agent
  │    db/database/sql/... → dba_agent
  │    k8s/kubernetes/pod/... → k8s_agent
  │    network/ping/dns/... → network_agent
  │    code/review/git/... → claude_dev_agent
  ├─ LLM (Claude Haiku, optional) → best-fit agent
  └─ no match → broadcast to all agents
```

Agent-to-agent: if an agent's reply contains `@other_agent_name`, the hub automatically dispatches to that agent.

---

## Environment Variables

```env
# backend/.env  (copy from .env.example)
ANTHROPIC_API_KEY=sk-ant-...   # optional — enables LLM routing fallback
FRONTEND_URL=http://localhost:5173
```

---

## Planned

- [ ] Message persistence (PostgreSQL)
- [ ] Network Agent
- [ ] Claude Dev Agent (code review, PR summaries)
- [ ] Secretary Agent (daily briefings, task orchestration)
