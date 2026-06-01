#!/usr/bin/env bash
# Run DeepAgent MACP bridge from WSL.
# Usage: bash run_deepagent.sh [IP_OR_URL] [LANGGRAPH_URL]
#
# Examples:
#   bash run_deepagent.sh                              # auto-detect Windows IP
#   bash run_deepagent.sh 10.x.x.x                    # explicit Windows IP
#   bash run_deepagent.sh ws://10.x.x.x:8010/ws/agent
set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

# Prefer the real Windows IP (non-172.x WSL gateway) from routing table
GW=$(ip route | grep default | awk '{print $3}' | grep -v '^172\.' | head -1)
if [ -z "$GW" ]; then
  GW=$(ip route | grep default | awk '{print $3}' | head -1)
fi

ARG1="${1:-}"
if [[ "$ARG1" == ws://* ]]; then
  SERVER="$ARG1"
elif [[ "$ARG1" =~ ^[0-9]+\.[0-9]+\.[0-9]+\.[0-9]+$ ]]; then
  SERVER="ws://${ARG1}:8010/ws/agent"
  GW="$ARG1"
else
  SERVER="ws://${GW}:8010/ws/agent"
fi

LANGGRAPH_URL="${2:-http://localhost:2024}"

# bypass corporate proxy for local Windows host and LangGraph
export no_proxy="localhost,127.0.0.1,${GW}"
export NO_PROXY="$no_proxy"

# auto-discover assistant ID if not set
if [ -z "$DEEPAGENT_ASSISTANT_ID" ]; then
  echo "[dba_agent] fetching assistant ID from ${LANGGRAPH_URL}..."
  DEEPAGENT_ASSISTANT_ID=$(curl -sf -X POST "${LANGGRAPH_URL}/assistants/search" \
    -H "Content-Type: application/json" -d '{"limit":1}' | python3 -c "
import sys, json
data = json.load(sys.stdin)
if data: print(data[0]['assistant_id'])
" 2>/dev/null || true)
  if [ -z "$DEEPAGENT_ASSISTANT_ID" ]; then
    echo "[dba_agent] ERROR: could not auto-discover assistant ID."
    echo "  Is LangGraph running at ${LANGGRAPH_URL}?"
    echo "  Try: curl -X POST ${LANGGRAPH_URL}/assistants/search -H 'Content-Type: application/json' -d '{\"limit\":1}'"
    echo "  Then: DEEPAGENT_ASSISTANT_ID=<uuid> bash $0"
    exit 1
  fi
  echo "[dba_agent] found assistant: ${DEEPAGENT_ASSISTANT_ID}"
fi
export DEEPAGENT_ASSISTANT_ID

echo "[dba_agent] connecting to $SERVER"
exec python3 "$SCRIPT_DIR/deepagent_wrapper.py" --server "$SERVER"
