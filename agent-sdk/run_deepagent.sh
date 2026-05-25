#!/usr/bin/env bash
# Run DeepAgent MACP bridge from WSL.
# Usage: bash run_deepagent.sh [MACP_SERVER_URL] [LANGGRAPH_URL]
#
# Examples:
#   bash run_deepagent.sh                              # auto-detect Windows IP
#   bash run_deepagent.sh ws://192.168.1.100:8010/ws/agent
#   DEEPAGENT_ASSISTANT_ID=abc123 bash run_deepagent.sh
set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
GW=$(ip route | grep default | awk '{print $3}' | head -1)

SERVER="${1:-ws://${GW}:8010/ws/agent}"
LANGGRAPH_URL="${2:-http://localhost:2024}"

# bypass corporate proxy for local Windows host and LangGraph
export no_proxy="localhost,127.0.0.1,${GW}"
export NO_PROXY="$no_proxy"

# auto-discover assistant ID if not set
if [ -z "$DEEPAGENT_ASSISTANT_ID" ]; then
  echo "[dba_agent] fetching assistant ID from ${LANGGRAPH_URL}..."
  DEEPAGENT_ASSISTANT_ID=$(curl -sf "${LANGGRAPH_URL}/assistants" | python3 -c "
import sys, json
data = json.load(sys.stdin)
if data: print(data[0]['assistant_id'])
" 2>/dev/null || true)
  if [ -z "$DEEPAGENT_ASSISTANT_ID" ]; then
    echo "[dba_agent] ERROR: could not auto-discover assistant ID."
    echo "  Is LangGraph running at ${LANGGRAPH_URL}?"
    echo "  Try: curl ${LANGGRAPH_URL}/assistants"
    echo "  Then: DEEPAGENT_ASSISTANT_ID=<uuid> bash $0"
    exit 1
  fi
  echo "[dba_agent] found assistant: ${DEEPAGENT_ASSISTANT_ID}"
fi
export DEEPAGENT_ASSISTANT_ID

echo "[dba_agent] connecting to $SERVER"
exec python3 "$SCRIPT_DIR/deepagent_wrapper.py" --server "$SERVER"
