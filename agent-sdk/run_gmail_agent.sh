#!/usr/bin/env bash
# Run gmail_agent MACP bridge on Ubuntu.
# Requires local LangGraph gmail agent running (auto-discovers port).
#
# Usage: bash run_gmail_agent.sh WINDOWS_IP [LANGGRAPH_URL]
#
# Examples:
#   bash run_gmail_agent.sh 10.x.x.x
#   bash run_gmail_agent.sh 10.x.x.x http://localhost:49137
set -e

WINDOWS_IP="${1:?Usage: $0 WINDOWS_IP [LANGGRAPH_URL]}"
LANGGRAPH_URL="${2:-}"
MACP_SERVER="ws://${WINDOWS_IP}:8010/ws/agent"
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

export no_proxy="localhost,127.0.0.1,${WINDOWS_IP}"
export NO_PROXY="$no_proxy"

# auto-discover LangGraph port if not specified
if [ -z "$LANGGRAPH_URL" ]; then
  echo "[gmail_agent] auto-discovering LangGraph port..."
  for port in 49137 2025 2026 3001 8080; do
    if curl -sf --max-time 2 "http://localhost:${port}/ok" > /dev/null 2>&1; then
      LANGGRAPH_URL="http://localhost:${port}"
      echo "[gmail_agent] found LangGraph at ${LANGGRAPH_URL}"
      break
    fi
  done
  if [ -z "$LANGGRAPH_URL" ]; then
    echo "[gmail_agent] ERROR: could not find LangGraph. Specify URL manually: $0 ${WINDOWS_IP} http://localhost:<port>"
    exit 1
  fi
fi

# get assistant ID
ASSISTANT_ID=$(curl -sf -X POST "${LANGGRAPH_URL}/assistants/search" \
  -H "Content-Type: application/json" -d '{"limit":1}' | python3 -c "
import sys, json
data = json.load(sys.stdin)
if data: print(data[0]['assistant_id'])
" 2>/dev/null || true)

if [ -z "$ASSISTANT_ID" ]; then
  echo "[gmail_agent] ERROR: could not get assistant ID from ${LANGGRAPH_URL}"
  exit 1
fi
echo "[gmail_agent] assistant: ${ASSISTANT_ID}"
echo "[gmail_agent] connecting to MACP at ${MACP_SERVER}"

exec uv run \
  --with httpx \
  --with websockets \
  python "$SCRIPT_DIR/gmail_agent_wrapper.py" \
  --server    "$MACP_SERVER" \
  --langgraph "$LANGGRAPH_URL" \
  --assistant "$ASSISTANT_ID"
