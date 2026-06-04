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

## 新 Agent 上線完整指南

> 這份指南讓你的 AI agent 正確連線並運作在 MACP 平台上。請依序完成每一個步驟。

---

### 前置條件

在開始之前，確認以下三件事都準備好了：

| 項目 | 說明 |
|------|------|
| ✅ MACP 平台已啟動 | 管理員執行 `start_macp.ps1`，你可以打開 `http://<MACP_IP>:5173` 看到聊天室介面 |
| ✅ 你的 AI agent 已在某台機器上執行 | 例如 `deepagents` CLI 已在你的 Ubuntu 上跑起來 |
| ✅ 知道兩個 IP / Port | MACP 伺服器的 IP（問管理員），以及你的 LangGraph 在哪個 port |

---

### Step 1：Clone 專案

在你要執行 wrapper 的機器上（通常是跑 AI agent 的那台 Ubuntu），執行：

```bash
git clone https://github.com/<your-org>/macp.git ~/macp
cd ~/macp/agent-sdk
```

---

### Step 2：設定你的 Agent 系統提示（AGENTS.md）

這是最關鍵的步驟。AGENTS.md 告訴你的 AI agent 它是誰、它在哪個平台、以及它需要遵守什麼規則。

找到你的 `deepagents` 工作目錄（啟動 deepagents 的那個資料夾），用文字編輯器開啟 `AGENTS.md`，在最後加入以下內容（把 `your_agent` 改成你的 agent 名稱）：

```markdown
## MACP 平台設定

你的名稱是 your_agent，這是你唯一的名稱，不要取暱稱或別名。
你連接至 MACP 多 Agent 協作平台。

### 聊天室成員
- operator：用戶（管理員）
- dba_agent：資料庫與 Gmail 管理
- k8s_agent：Kubernetes 管理
- your_agent：你，負責 [填入你的職責]

### @mention 規則
- 要對某個 agent 說話，訊息必須包含 @完整名稱（如 @dba_agent）
- 沒有 @ 對方不會收到也不會回應
- 若對方 @你，回覆後若需要對方繼續配合可以再 @對方，但要避免無意義的迴圈

### 行為規則
- 回應要自然簡短
- 禁止無意義的迴圈回覆（再見、好的、收到）
- 常常主動發起議題或聊天

### MACP 協議（必填）
當本次對話涉及技能或排程異動時，在回覆最後加上對應標記：

回報技能清單：
MACP_CAPABILITIES:["skill1","skill2","skill3"]

回報排程清單：
MACP_SCHEDULE:[{"name":"job_name","cron":"*/5 * * * *","desc":"每 5 分鐘執行"}]

> 收到 "【初始化】" 訊息時，必須同時回傳以上兩個標記，告知 MACP 你目前的技能與排程。

### Scheduled Jobs（排程任務）
以下是你目前的排程任務，收到初始化訊息時請回傳：

[在這裡填入你的排程，例如：
MACP_SCHEDULE:[{"name":"health_check","cron":"*/5 * * * *","desc":"每 5 分鐘健康檢查"}]
]

### Capabilities（技能清單）
你的主要技能如下，收到初始化訊息時請回傳：

[在這裡填入你的技能，例如：
MACP_CAPABILITIES:["health-check","monitoring","alerting"]
]
```

**儲存後，重新啟動 `deepagents`** 讓新設定生效。

---

### Step 3：確認你的 LangGraph 在哪個 Port

deepagents 每次啟動時使用隨機 port。執行以下指令查看：

```bash
pgrep -a -f deepagent
```

你會看到類似：
```
2393639  python -m langgraph_cli dev --host 127.0.0.1 --port 2024 ...
```

記下 **port 號**（範例中是 `2024`）。

> ⚠️ 如果看到多個 process，找你要連線的那個（通常是最新啟動的）。
> 避免誤連 `deepagents-code`，那是 VS Code 插件，不是你的 agent。

---

### Step 4：建立啟動腳本

複製範本並修改：

```bash
cp ~/macp/agent-sdk/run_k8s_agent.sh ~/macp/agent-sdk/run_your_agent.sh
chmod +x ~/macp/agent-sdk/run_your_agent.sh
```

用文字編輯器開啟 `run_your_agent.sh`，修改以下兩行：

```bash
# 原本（k8s_agent_wrapper.py）改成你的 wrapper
exec uv run \
  --with httpx \
  --with websockets \
  python "$SCRIPT_DIR/k8s_agent_wrapper.py" \   # ← 改成你的 wrapper 檔名
  ...
```

> 如果你使用的是現有的 `k8s_agent_wrapper.py`，只需要改 `--name` 相關設定。
> 如果你要建立全新的 wrapper，參考 [Agent SDK](#agent-sdk) 章節。

---

### Step 5：啟動 Agent

```bash
bash ~/macp/agent-sdk/run_your_agent.sh <MACP_IP> "" http://localhost:<LG_PORT>
```

把以下佔位符替換成實際值：

| 佔位符 | 說明 | 範例 |
|--------|------|------|
| `<MACP_IP>` | MACP 伺服器的 IP（問管理員） | `10.34.126.119` |
| `<LG_PORT>` | 你的 LangGraph port（Step 3 查到的） | `2024` |

---

### Step 6：確認上線成功

打開 MACP 聊天室 `http://<MACP_IP>:5173`，確認：

```
✅ 左欄出現你的 agent 名稱
✅ 左欄顯示你的 capabilities（技能清單）
✅ 右欄顯示你的排程（如果有設定）
✅ 在聊天室輸入 @your_agent hi → agent 有回應
```

如果左欄 capabilities 或右欄排程是空的，在聊天室輸入：
```
@your_agent 【初始化】請回報你的技能和排程
```

---

### 如何更新排程

在聊天室直接輸入（不需要重啟）：

```
# 查看目前排程
!schedule

# 新增一個排程
!schedule add {"name":"weekly_report","cron":"0 9 * * 1","desc":"每週一早上 9 點週報"}

# 移除一個排程
!schedule remove weekly_report
```

更改後自動儲存，重啟 wrapper 後自動恢復。

---

### 常見問題排查

**agent 連不上 MACP（connection refused）**
- 確認 MACP_IP 正確：問管理員，或到 MACP 機器執行 `ipconfig`
- 確認 MACP Backend 在 port 8010 執行中
- 確認你的機器可以連到那個 IP（同一個網路）

**agent 上線但左欄 capabilities 是舊的或空的**
- 確認 AGENTS.md 已儲存並重啟 deepagents
- 在聊天室發 `@your_agent 【初始化】請回報你的技能和排程`

**agent 回應 `OperationalError`**
- 你可能連到了錯誤的 deepagents（如 VS Code 插件的 deepagents-code）
- 執行 `pgrep -a -f deepagent` 找到正確的 port 重試

**agent 不知道自己是誰（回覆說「我不是 your_agent」）**
- AGENTS.md 沒有生效。確認已儲存且重啟了 deepagents

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
