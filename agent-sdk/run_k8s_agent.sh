#!/usr/bin/env bash
# Run k8s_agent MACP bridge on Ubuntu.
# Usage: bash run_k8s_agent.sh WINDOWS_IP [ASSISTANT_ID] [LANGGRAPH_URL]
#
# Examples:
#   bash run_k8s_agent.sh 192.168.1.100
#   bash run_k8s_agent.sh 192.168.1.100 abc123-def456
#   bash run_k8s_agent.sh 192.168.1.100 abc123-def456 http://localhost:2024
set -e

WINDOWS_IP="${1:?Usage: $0 WINDOWS_IP [ASSISTANT_ID] [LANGGRAPH_URL]}"
ASSISTANT_ID="${2:-}"
LANGGRAPH_URL="${3:-http://localhost:2024}"
MACP_SERVER="ws://${WINDOWS_IP}:8010/ws/agent"

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

# bypass proxy for local LangGraph and remote MACP
export no_proxy="localhost,127.0.0.1,${WINDOWS_IP}"
export NO_PROXY="$no_proxy"

# auto-discover assistant ID if not provided
if [ -z "$ASSISTANT_ID" ]; then
  echo "[k8s_agent] fetching assistant ID from ${LANGGRAPH_URL}..."
  ASSISTANT_ID=$(curl -sf "${LANGGRAPH_URL}/assistants" | python3 -c "
import sys, json
data = json.load(sys.stdin)
if data: print(data[0]['assistant_id'])
" 2>/dev/null || true)
  if [ -z "$ASSISTANT_ID" ]; then
    echo "[k8s_agent] ERROR: could not auto-discover assistant ID."
    echo "  Run: curl ${LANGGRAPH_URL}/assistants"
    echo "  Then: $0 ${WINDOWS_IP} <assistant_id>"
    exit 1
  fi
  echo "[k8s_agent] found assistant: ${ASSISTANT_ID}"
fi

echo "[k8s_agent] connecting to MACP at ${MACP_SERVER}"

exec uv run \
  --with httpx \
  --with websockets \
  python "$SCRIPT_DIR/k8s_agent_wrapper.py" \
  --server    "$MACP_SERVER" \
  --langgraph "$LANGGRAPH_URL" \
  --assistant "$ASSISTANT_ID"
