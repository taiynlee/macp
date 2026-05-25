# MACP — Implementation Plan

> 勾選完成的項目即可追蹤進度。

---

## Phase 1 — Infrastructure + WebSocket Hub ✅

- [x] 建立 `backend/` uv 專案（`pyproject.toml`）
- [x] 安裝依賴：fastapi, uvicorn, websockets, anthropic, pydantic-settings
- [x] 建立 `backend/app/main.py`（FastAPI app 入口）
- [x] 建立 `backend/app/api/ws.py`（WebSocket hub — in-process broadcast，移除 Redis）
- [x] 掛載 WebSocket router 到 main.py
- [x] 建立 `backend/.env.example`（環境變數範本）
- [x] 驗證：uvicorn 啟動，多個 WebSocket client 能互傳訊息

---

## Phase 2 — Agent Registry（Name-Based）✅

- [x] 建立 `backend/app/core/registry.py`（在線 agent 追蹤：name, capabilities, heartbeat, schedule）
- [x] 建立 `backend/app/api/agents.py`（REST：GET `/api/agents`）
- [x] WebSocket `/ws/agent?name=<name>` — register / heartbeat / broadcast
- [x] WebSocket `/ws?name=<name>` — UI 使用者端
- [x] agent 斷線後從 registry 消失並 broadcast 通知

---

## Phase 3 — Agent SDK Wrapper ✅

- [x] 建立 `agent-sdk/wrapper.py`（AgentWrapper 基底類別）
  - [x] 連線 + 重連邏輯（exponential backoff）
  - [x] 自動 register
  - [x] 心跳（每 30s）
  - [x] 接收 task → `handle_task()` → 回傳 report
  - [x] `send_alert()` / `send_schedule()` / `report_job()` helper
  - [x] 內建 cron 排程器（`_job_scheduler`，解析 `*/N` 格式）
  - [x] cross-agent visibility（non-task 訊息不過濾 target）
- [x] 建立 `agent-sdk/example_agent.py`

---

## Phase 4 — Orchestrator ✅

- [x] 建立 `backend/app/core/orchestrator.py`
  - [x] 關鍵字路由（db / k8s / network / code，含中文關鍵字）
  - [x] LLM 路由（Claude Haiku，ANTHROPIC_API_KEY 有設定才啟用）
  - [x] no match → broadcast all agents
- [x] Agent-to-agent routing：agent report 含 `@mention` 自動 dispatch
- [x] Task envelope 含 `original_sender`，讓 agent 知道要 reply 給誰

---

## Phase 5 — React Web UI ✅

- [x] 建立 `frontend/` Vite + React + TypeScript 專案
- [x] `useWebSocket.ts` — WebSocket hook
- [x] `MessageFeed.tsx` — 聊天訊息串列，per-agent 色系，表格對齊，長文自動換行
- [x] `AgentList.tsx` — sidebar，octagon avatar，SVG icon（DB/K8s/Net/Code），全 skill 展開
- [x] `ChatRoom.tsx` — @mention dropdown，↑↓ 歷史導航，標題自訂
- [x] `AnnouncementBoard.tsx` — 右側公告欄，per-agent 色系排程，✓/✗ job 狀態
- [x] `Avatar.tsx` — 依 agent 類型顯示 SVG icon，octagon clip-path，hue glow
- [x] `utils/color.ts` — 6 色色盤，跨元件共用
- [x] `index.css` — 深藍 dark theme，design token 系統

---

## Phase 6 — Message Persistence（PostgreSQL）

- [ ] 建立 `backend/app/db/session.py`
- [ ] 建立 `backend/app/models/message.py`
- [ ] Alembic migration
- [ ] `GET /api/messages` history endpoint
- [ ] ws.py 收到訊息時寫入 DB

---

## Phase 7 — DBA Agent（dba_agent）✅

- [x] `agent-sdk/deepagent_wrapper.py`
  - [x] 轉發 task → LangGraph `runs/wait`
  - [x] interrupt/approval → 自動 approve
  - [x] persistent thread（跨對話記憶），`!reset` 清除
  - [x] context 注入（聊天室記錄 + 系統資訊 + reply 提示）
  - [x] cron 排程（connection_check ping LangGraph）
- [x] proxy bypass（WSL → Windows IP）
- [x] 驗證：dba_agent 上線，回答 DB 相關問題，agent-to-agent 對話

---

## Phase 8 — 其他 Agent 上線

- [x] **K8s Agent**（另一台 Ubuntu + LangGraph）
  - [x] `agent-sdk/k8s_agent_wrapper.py`
  - [x] `agent-sdk/run_k8s_agent.sh`（auto-discover assistant ID）
  - [x] cron 排程（pod_health_check）
- [ ] Network Agent
- [ ] Claude Dev Agent（code review, PR summaries）
- [ ] Secretary Agent（daily briefing, task orchestration）

---

## 當前狀態

| Phase | 狀態 |
|-------|------|
| 1 — WebSocket Hub | ✅ 完成 |
| 2 — Agent Registry | ✅ 完成 |
| 3 — Agent SDK | ✅ 完成 |
| 4 — Orchestrator | ✅ 完成 |
| 5 — React Web UI | ✅ 完成 |
| 6 — Message Persistence | 未開始 |
| 7 — DBA Agent | ✅ 完成 |
| 8 — K8s Agent | ✅ 完成；其他 agent 待上線 |
