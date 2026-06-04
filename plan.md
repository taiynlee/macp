# MACP — Implementation Plan

> 勾選完成的項目即可追蹤進度。

---

## Phase 1 — Infrastructure + WebSocket Hub ✅

- [x] 建立 `backend/` uv 專案（`pyproject.toml`）
- [x] 安裝依賴：fastapi, uvicorn, websockets, anthropic, pydantic-settings
- [x] 建立 `backend/app/main.py`（FastAPI app 入口）
- [x] 建立 `backend/app/api/ws.py`（WebSocket hub — in-process broadcast）
- [x] 掛載 WebSocket router 到 main.py
- [x] 建立 `backend/.env.example`
- [x] 驗證：uvicorn 啟動，多個 WebSocket client 能互傳訊息

---

## Phase 2 — Agent Registry ✅

- [x] 建立 `backend/app/core/registry.py`（在線 agent 追蹤：name, capabilities, heartbeat, schedule）
- [x] 建立 `backend/app/api/agents.py`（REST：GET `/api/agents`）
- [x] WebSocket `/ws/agent?name=<name>` — register / heartbeat / broadcast
- [x] WebSocket `/ws?name=<name>` — UI 使用者端
- [x] agent 斷線後從 registry 消失並 broadcast 通知

---

## Phase 3 — Agent SDK Wrapper ✅

- [x] 建立 `agent-sdk/wrapper.py`（AgentWrapper 基底類別）
  - [x] 連線 + 重連（exponential backoff）
  - [x] 自動 register
  - [x] 心跳（每 30s）
  - [x] task → `handle_task()` → report
  - [x] `send_alert()` / `send_schedule()` / `update_capabilities()` / `report_job()` helpers
  - [x] 內建 cron 排程器（`_job_scheduler`，解析 `*/N` 格式）
- [x] 建立 `agent-sdk/example_agent.py`

---

## Phase 4 — Orchestrator ✅

- [x] 建立 `backend/app/core/orchestrator.py`
  - [x] 關鍵字路由（db / k8s / network / code，含中文）
  - [x] LLM 路由（Claude Haiku，ANTHROPIC_API_KEY 有設定才啟用）
  - [x] no match → broadcast all agents
- [x] Agent-to-agent routing（`@mention` → auto dispatch，one hop）
- [x] Task envelope 含 `original_sender`

---

## Phase 5 — React Web UI ✅

- [x] Vite + React + TypeScript 專案
- [x] `useWebSocket.ts` — WebSocket hook，refresh on `capabilities_updated` + `schedule_updated`
- [x] `MessageFeed.tsx` — per-agent 色系，表格/程式碼塊，長文換行
- [x] `AgentList.tsx` — octagon avatar，capabilities 標籤，可接受外部 width style
- [x] `ChatRoom.tsx` — @mention dropdown，↑↓ 歷史導航，可拖曳面板寬度
- [x] `AnnouncementBoard.tsx` — per-agent 色系排程，✓/✗ job 狀態，可接受外部 width style
- [x] `Avatar.tsx` — SVG icon，octagon clip-path
- [x] `utils/color.ts` — 6 色色盤
- [x] `index.css` — 深藍 dark theme + 淺色模式，design token，可拖曳 resizer 樣式
- [x] **可拖曳側欄邊界**（`useResizable` hook，localStorage 保存寬度）
- [x] 定期 10 秒 poll agents（補漏 schedule_updated events）

---

## Phase 6 — Message Persistence（PostgreSQL）

- [ ] 建立 `backend/app/db/session.py`
- [ ] 建立 `backend/app/models/message.py`
- [ ] Alembic migration
- [ ] `GET /api/messages` history endpoint
- [ ] ws.py 收到訊息時寫入 DB

---

## Phase 7 — DBA Agent ✅

- [x] `agent-sdk/deepagent_wrapper.py`
  - [x] 轉發 task → LangGraph `runs/wait`
  - [x] interrupt/approval → 自動 approve
  - [x] persistent thread（跨對話記憶），`!reset` 清除
  - [x] `_extract_text()` — 處理 list content、`<think>` 區塊 fallback
  - [x] `__error__` → 顯示有意義的錯誤訊息
  - [x] **MACP 雙 marker 協議**：
    - on_connect 發 init query，agent 回報 `MACP_CAPABILITIES` + `MACP_SCHEDULE`
    - 每次對話 prefix 帶 `_MACP_PROTOCOL` 指引
    - `_apply_markers()` 自動解析、更新 capabilities/schedule、持久化到檔案
  - [x] **`!schedule` 指令**：add / remove / list / 整批替換，存入 `dba_schedule.json`
  - [x] 排程 fallback 優先序：MACP marker → `dba_schedule.json` → `_DEFAULT_SCHEDULE`
- [x] `agent-sdk/run_dba_agent.sh`（auto-detect Windows IP + assistant ID）
- [x] proxy bypass（WSL → Windows IP）

---

## Phase 8 — 其他 Agent 上線

- [x] **K8s Agent**（遠端 Ubuntu + LangGraph deepagents-cli）
  - [x] `agent-sdk/k8s_agent_wrapper.py`（對齊 dba 架構）
    - [x] MACP 雙 marker 協議（同 dba）
    - [x] `!schedule` 指令，存入 `k8s_schedule.json`
    - [x] `_extract_text()` — list content + think fallback
    - [x] `__error__` → 顯示有意義錯誤
    - [x] prefix 含身份資訊（在 AGENTS.md 設定前的 fallback）
  - [x] `agent-sdk/run_k8s_agent.sh`（auto-discover assistant ID）
  - [x] `agent-sdk/k8s_schedule.json`（持久化排程）
  - [x] 診斷：deepagents-code vs deepagents-cli port 區分
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
| 5 — React Web UI | ✅ 完成（含可拖曳側欄） |
| 6 — Message Persistence | 未開始 |
| 7 — DBA Agent | ✅ 完成 |
| 8 — K8s Agent | ✅ 完成；其他 agent 待上線 |

---

## 技術債 / Known Issues

- deepagents 每次啟動使用隨機 port，需手動指定給 `run_k8s_agent.sh`（或設定固定 port）
- MACP marker init query 效果取決於 AGENTS.md 設定；若 agent 未設定 `!init` handler，需手動 `!schedule` 一次
- LangGraph thread 隔離：init query 使用新 thread，無法讀取跨 thread 記憶
