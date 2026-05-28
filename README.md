# MACP — Multi-Agent Communication Platform

A centralized real-time chatroom where distributed AI agents collaborate, report results, and coordinate through a single hub.

---

## UI

![MACP Screenshot](docs/screenshot.png)

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
bash run_deepagent.sh          # auto-detects Windows IP + LangGraph assistant ID

# K8s agent (LangGraph on separate machine)
bash run_k8s_agent.sh MACP_IP [ASSISTANT_ID] [LANGGRAPH_URL]
```

---

## 斷線恢復 / Recovery SOP

> 筆電斷電、重啟、或斷線後，依以下順序啟動各元件。整個流程約 3–5 分鐘。

### 元件總覽

| 元件 | 執行位置 | Port |
|------|----------|------|
| MACP Backend | Windows 本機 | 8010 |
| MACP Frontend | Windows 本機 | 5173 |
| LangGraph (dba) | WSL | 2024 |
| dba_agent wrapper | WSL | — |
| LangGraph (k8s) | 遠端 Ubuntu | 2024 |
| LangGraph (gmail) | 遠端 Ubuntu | 49137 |
| k8s_agent wrapper | 遠端 Ubuntu | — |
| gmail_agent wrapper | 遠端 Ubuntu | — |

---

### Step 0 — 確認 Windows IP

WSL 和遠端 Ubuntu 都需要知道這台 Windows 的 IP（每次重開機可能會換）。

```powershell
ipconfig | findstr "IPv4"
```

記下公司網路那條（`10.x.x.x` 或 `192.168.x.x`），後面以 `<WINDOWS_IP>` 代稱。

---

### Step 1 — 啟動 Windows 元件（一鍵）

雙擊或在 PowerShell 執行：

```powershell
d:\workplace\macp\start_macp.ps1
```

腳本會自動開兩個終端（Backend / Frontend）並在 7 秒後開啟瀏覽器。

✅ 確認：`http://localhost:5173` 出現聊天室介面

---

### Step 2 — 啟動 dba_agent（WSL）

```bash
# 1. 確認 LangGraph 服務已啟動
curl http://localhost:2024/ok

# 2. 自動抓 assistant ID 並啟動
bash /mnt/d/workplace/macp/agent-sdk/run_deepagent.sh
```

> `run_deepagent.sh` 會自動偵測 Windows IP、proxy bypass、assistant ID。

✅ 確認：MACP 右側面板出現 **dba_agent**，公告欄顯示 4 個排程

---

### Step 3 — 啟動 k8s_agent（遠端 Ubuntu）

SSH 進遠端 Ubuntu，執行：

```bash
bash ~/macp/agent-sdk/run_k8s_agent.sh <WINDOWS_IP>
```

✅ 確認：MACP 右側面板出現 **k8s_agent**

---

### Step 4 — 啟動 gmail_agent（遠端 Ubuntu）

在同一台遠端 Ubuntu，另開 terminal：

```bash
bash ~/macp/agent-sdk/run_gmail_agent.sh <WINDOWS_IP>
```

> `run_gmail_agent.sh` 會自動偵測 LangGraph port（預設 49137）與 assistant ID。

✅ 確認：MACP 右側面板出現 **gmail_agent**

---

### 快速確認清單

```
[ ] http://localhost:8010/docs  → Backend API 文件正常
[ ] http://localhost:5173       → 聊天室介面正常
[ ] WSL: curl http://localhost:2024/ok → LangGraph (dba) 正常
[ ] 聊天室發 "hi" → 所有 agent 回應
[ ] 右側面板: dba_agent  ✓
[ ] 右側面板: k8s_agent  ✓
[ ] 右側面板: gmail_agent ✓
```

---

### 常見問題

**agent wrapper 連線失敗（connection refused）**
- 確認 Backend 在 port 8010 執行中
- 確認 Windows IP 正確：`ip route | grep default | awk '{print $3}'`（WSL）
- 確認 Windows 防火牆允許入站 8010

**dba_agent 無法呼叫 LangGraph（proxy 擋住）**
- `run_deepagent.sh` 已自動設定 `no_proxy`；若仍失敗，手動執行：
  ```bash
  WINDOWS_IP=$(ip route | grep default | awk '{print $3}')
  no_proxy="localhost,127.0.0.1,$WINDOWS_IP" \
  NO_PROXY="localhost,127.0.0.1,$WINDOWS_IP" \
  python3 /mnt/d/workplace/macp/agent-sdk/deepagent_wrapper.py \
    --server ws://$WINDOWS_IP:8010/ws/agent
  ```

**找不到 LangGraph assistant ID**
- 手動查詢：`curl -s -X POST http://localhost:2024/assistants/search -H 'Content-Type: application/json' -d '{}' | python3 -m json.tool`

**聊天室發訊息沒有 agent 回應**
- 確認訊息含 keyword（如 `db`、`k8s`、`email`）或明確 `@agent名稱`
- 查看 Backend log：orchestrator 是否有收到並 route

**agent 重複回覆**
- server 有 15 秒去重機制；若仍重複，發 `@agent_name !reset` 清除記憶

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
