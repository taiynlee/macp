#!/usr/bin/env bash
# Run DeepAgent MACP bridge from WSL.
# Usage: bash run_deepagent.sh [MACP_SERVER_URL]
set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
SERVER="${1:-}"

if [ -z "$SERVER" ]; then
  GW=$(ip route | grep default | awk '{print $3}' | head -1)
  SERVER="ws://${GW}:8010/ws/agent"
fi

echo "[dba_agent] connecting to $SERVER"

# bypass corporate proxy for local Windows host
GW=$(ip route | grep default | awk '{print $3}' | head -1)
export no_proxy="localhost,127.0.0.1,${GW}"
export NO_PROXY="$no_proxy"

exec ~/.local/bin/uv run \
  --with httpx \
  --with websockets \
  python "$SCRIPT_DIR/deepagent_wrapper.py" --server "$SERVER"
