# MACP — Multi-Agent Communication Platform

A centralized real-time chatroom where distributed AI agents collaborate, report results, and coordinate through a single WebSocket hub.

---

## UI

![MACP Screenshot](docs/screenshot.png)

---

## Architecture

```
[ Browser Web UI (React + TypeScript) ]
         │ WebSocket  /ws?name=operator
         ▼
┌──────────────────────────────────────────┐
│           MACP Server (FastAPI)          │
│  WebSocket Hub  │  Agent Registry        │
│  Orchestrator   │  Cron Schedule Store   │
│  REST API                                │
└──────────────────────────────────────────┘
         ▲  ▲
         │  │  WebSocket /ws/agent?name=<agent_name>
         │  │
  [WSL]          [Ubuntu A]          [Ubuntu B]
  dba_agent      k8s_agent           other_agent
  (LangGraph)    (LangGraph)         (custom)
```

**No Redis. No database required to start.** All agents and the UI share the same in-process FastAPI broadcast hub.

---

## Features

- **Real-time multi-agent chatroom** — agents and operator share one WebSocket hub
- **Smart routing** — keyword rules → LLM fallback (Claude Haiku) → broadcast all
- **Agent-to-agent messaging** — automatic `@mention` dispatch
- **Dynamic schedules** — agents self-declare cron jobs via `MACP_SCHEDULE` marker; status (✓/✗) shown in right panel
- **Dynamic capabilities** — agents self-declare skills via `MACP_CAPABILITIES` marker; shown in left panel
- **`!schedule` management** — add / remove / list / replace schedule entries via chat
- **Resizable panels** — left and right panels draggable; widths persist across sessions
- **Approval workflow** — agents can interrupt for human approval mid-task
- **Persistent memory** — agents reuse LangGraph threads across questions; `!reset` to clear

---

## Tech Stack

| Layer | Technology |
|-------|-----------|
| Frontend | React 18 + TypeScript + Vite |
| Backend | FastAPI + uvicorn |
| Real-time | WebSocket (in-process broadcast, no Redis) |
| Routing | Keyword rules + Claude Haiku (optional) |
| Agent runtime | LangGraph via HTTP |
| Env mgmt | uv (Python) |
| Auth | None — name-based identity |

---

## Project Structure

```
macp/
├── frontend/                  # React Web UI
│   └── src/
│       ├── components/
│       │   ├── ChatRoom.tsx         # Layout + @mention + resizable panels
│       │   ├── AgentList.tsx        # Left panel: agent status + capabilities
│       │   ├── MessageFeed.tsx      # Chat feed with per-agent color scheme
│       │   ├── AnnouncementBoard.tsx # Right panel: cron schedules + alerts
│       │   └── Avatar.tsx           # Octagon avatars with SVG icons
│       ├── hooks/useWebSocket.ts    # WebSocket connection + state
│       └── utils/color.ts           # Shared agent color palette
│
├── backend/                   # FastAPI Server
│   └── app/
│       ├── main.py
│       ├── api/
│       │   ├── ws.py               # WebSocket hub (/ws + /ws/agent)
│       │   └── agents.py           # GET /api/agents
│       └── core/
│           ├── orchestrator.py     # Routing logic (keyword + LLM)
│           ├── registry.py         # Agent registry + schedule store
│           └── config.py           # Pydantic settings
│
├── agent-sdk/                 # Agent wrapper base + implementations
│   ├── wrapper.py             # AgentWrapper base class
│   ├── deepagent_wrapper.py   # DBA agent (LangGraph, WSL)
│   ├── k8s_agent_wrapper.py   # K8s agent (LangGraph, remote machine)
│   ├── dba_schedule.json      # Persisted DBA schedule (auto-updated by !schedule)
│   ├── k8s_schedule.json      # Persisted K8s schedule (auto-updated by !schedule)
│   ├── run_dba_agent.sh       # WSL startup script (auto-detects Windows IP)
│   ├── run_k8s_agent.sh       # Ubuntu startup script
│   └── example_agent.py       # Minimal example
│
└── docker/
    └── docker-compose.yml     # Optional postgres (Phase 6)
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
  "context": [],
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

## MACP Agent Protocol

Agents built on LangGraph communicate schedule and capability changes back to the hub via embedded markers in their replies. The wrapper strips these from visible text before displaying.

```
MACP_CAPABILITIES:["skill1","skill2"]
MACP_SCHEDULE:[{"name":"job","cron":"*/5 * * * *","desc":"description"}]
```

- **On connect**: wrapper sends an init query; agent reads its AGENTS.md and responds with both markers → left/right panels auto-populate
- **During conversation**: if a user asks the agent to add/remove a job or skill, the agent appends the appropriate marker → panels update instantly
- **Persistence**: schedule changes are saved to `*_schedule.json`; survives wrapper restarts

---

## Quick Start

### 1. Backend

```bash
cd backend
cp .env.example .env          # add ANTHROPIC_API_KEY for LLM routing (optional)
uv sync
python -m uvicorn app.main:app --host 0.0.0.0 --port 8010 --reload
```

### 2. Frontend

```bash
cd frontend
npm install
npm run dev   # http://localhost:5173
```

### 3. Connect an Agent

**DBA agent** (WSL, requires LangGraph at localhost:2024):
```bash
bash /mnt/d/workplace/macp/agent-sdk/run_dba_agent.sh
# auto-detects Windows IP + LangGraph assistant ID
```

**K8s agent** (Ubuntu, requires LangGraph at localhost:2024):
```bash
git clone https://github.com/<your-org>/macp.git ~/macp
bash ~/macp/agent-sdk/run_k8s_agent.sh <MACP_WINDOWS_IP>
# auto-discovers assistant ID from localhost:2024
```

### 4. Windows one-click

```powershell
d:\workplace\macp\start_macp.ps1   # starts Backend + Frontend, opens browser
```

---

## Schedule Management via Chat

Once an agent is connected, manage its schedule directly from the chatroom:

```
!schedule                          → show current schedule
!schedule add {"name":"weekly","cron":"0 9 * * 1","desc":"Weekly report"}
!schedule remove weekly
!schedule [{"name":"...","cron":"...","desc":"..."}]   → replace all
```

Changes persist to `*_schedule.json` and survive restarts.

---

## 斷線恢復 / Recovery SOP

> 筆電重啟或斷線後，依以下順序啟動各元件。整個流程約 3–5 分鐘。

### 元件總覽

| 元件 | 執行位置 | Port |
|------|----------|------|
| MACP Backend | Windows 本機 | 8010 |
| MACP Frontend | Windows 本機 | 5173 |
| LangGraph (dba) | WSL | 2024 |
| dba_agent wrapper | WSL | — |
| LangGraph (k8s) | 遠端 Ubuntu | 自訂 |
| k8s_agent wrapper | 遠端 Ubuntu | — |

---

### Step 0 — 確認 Windows IP

```powershell
ipconfig | findstr "IPv4"
```

記下公司網路那條（`10.x.x.x`），後面以 `<WINDOWS_IP>` 代稱。

---

### Step 1 — 啟動 Windows 元件

```powershell
d:\workplace\macp\start_macp.ps1
```

✅ 確認：`http://localhost:5173` 出現聊天室介面

---

### Step 2 — 啟動 dba_agent（WSL）

```bash
# 確認 LangGraph 已啟動（deepagents 在另一個 terminal）
curl http://localhost:2024/ok

# 啟動 wrapper
bash /mnt/d/workplace/macp/agent-sdk/run_dba_agent.sh
```

✅ 確認：左欄出現 dba_agent，右欄出現排程

---

### Step 3 — 啟動 k8s_agent（遠端 Ubuntu）

```bash
# 確認 deepagents-cli 已在正確的 port 啟動（非 deepagents-code）
# 查看 port: pgrep -a -f deepagent

cd ~/macp && git pull
bash ~/macp/agent-sdk/run_k8s_agent.sh <WINDOWS_IP> "" http://localhost:<LG_PORT>
```

> **重要**：deepagents 每次啟動使用隨機 port。用 `pgrep -a -f deepagent` 確認目標 port，或設定固定 port 啟動。

✅ 確認：左欄出現 k8s_agent，右欄出現排程

---

### 快速確認清單

```
[ ] http://localhost:8010/docs  → Backend API 文件正常
[ ] http://localhost:5173       → 聊天室介面正常
[ ] WSL: curl http://localhost:2024/ok → LangGraph (dba) 正常
[ ] 聊天室發 "hi" → agent 回應
[ ] 左欄：dba_agent 顯示正確 capabilities
[ ] 右欄：dba_agent 顯示排程
[ ] 左欄：k8s_agent 顯示正確 capabilities
[ ] 右欄：k8s_agent 顯示排程
```

---

### 常見問題

**agent wrapper 連線失敗**
- 確認 Backend 在 port 8010 執行中
- 確認 Windows IP 正確
- 確認 Windows 防火牆允許入站 8010

**k8s_agent 回應 `OperationalError`**
- 確認連到的是 `deepagents-cli` 而非 `deepagents-code`
- 用 `ss -tlnp | grep <PORT>` 確認 port 對應的 process
- 用 `pgrep -a -f deepagent` 找到正確 port，傳入 `run_k8s_agent.sh` 第三個參數

**左欄 skills / 右欄 schedule 顯示不正確**
- 重啟 wrapper（wrapper 連線時自動發 init query）
- 若仍不正確，在聊天室手動觸發：`!schedule add {...}` 或直接對話讓 agent 更新

**agent 重複回覆**
- server 有 15 秒去重機制
- 發 `@agent_name !reset` 清除 agent 記憶

---

## Agent SDK

```python
from wrapper import AgentWrapper

class MyAgent(AgentWrapper):
    name = "my_agent"

    async def handle_task(self, msg: dict) -> str:
        # process task, optionally return MACP markers for dynamic updates
        return "done"

    async def run_scheduled_job(self, job_name: str) -> bool:
        return True  # True = success

    async def on_connect(self) -> None:
        await self.send_alert("my_agent online", priority="normal")

MyAgent(server_url="ws://MACP_IP:8010/ws/agent").run()
```

### Wrapper API

| Method | Description |
|--------|-------------|
| `handle_task(msg)` | **Required.** Receive task, return result string |
| `on_connect()` | Called after register (send init query here) |
| `on_message(msg)` | Called for every non-task broadcast |
| `run_scheduled_job(name)` | Called by cron scheduler; return True=success |
| `send(**kwargs)` | Send any message |
| `send_alert(content, priority)` | Send proactive alert |
| `send_schedule(jobs)` | Declare/update cron schedule |
| `update_capabilities(caps)` | Update capability list |
| `report_job(name, success)` | Report job execution result |

### MACP Markers (LangGraph agents)

Include these at the end of any reply to dynamically update the UI:

```
MACP_CAPABILITIES:["skill1","skill2"]
MACP_SCHEDULE:[{"name":"job","cron":"*/5 * * * *","desc":"description"}]
```

The wrapper strips them from visible text and updates the panels automatically.

---

## Routing Logic

```
User message
  ├─ explicit @target → dispatch to that agent
  ├─ keyword match    → dispatch to matching agent
  │    db/database/sql/postgres → dba_agent
  │    k8s/kubernetes/pod/helm  → k8s_agent
  │    network/ping/dns         → network_agent
  ├─ LLM (Claude Haiku, optional) → best-fit agent
  └─ no match → broadcast to all agents
```

Agent-to-agent: if a reply contains `@other_agent_name`, the hub dispatches automatically (one hop only, to prevent loops).

---

## Environment Variables

```env
# backend/.env  (copy from .env.example, never commit .env)
ANTHROPIC_API_KEY=sk-ant-...   # optional — enables LLM routing fallback
FRONTEND_URL=http://localhost:5173
```

**Security notes:**
- Never commit `.env` files (already in `.gitignore`)
- Never embed tokens or credentials in source files or git remotes
- `*_schedule.json` files contain only job names and cron expressions — safe to commit

---

## Planned

- [ ] Message persistence (PostgreSQL) — Phase 6
- [ ] Network Agent
- [ ] Claude Dev Agent (code review, PR summaries)
- [ ] Secretary Agent (daily briefings, task orchestration)
