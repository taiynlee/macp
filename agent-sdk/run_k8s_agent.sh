#!/usr/bin/env bash
# Run k8s_agent MACP bridge on Ubuntu (no LangGraph required).
# Uses kubernetes Python client + Claude API directly.
#
# Usage: bash run_k8s_agent.sh WINDOWS_IP
# Env:   ANTHROPIC_API_KEY=sk-ant-...  (optional, enables AI reasoning)
#
# Examples:
#   bash run_k8s_agent.sh 10.x.x.x
#   ANTHROPIC_API_KEY=sk-ant-... bash run_k8s_agent.sh 10.x.x.x
set -e

WINDOWS_IP="${1:?Usage: $0 WINDOWS_IP}"
MACP_SERVER="ws://${WINDOWS_IP}:8010/ws/agent"
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

export no_proxy="localhost,127.0.0.1,${WINDOWS_IP}"
export NO_PROXY="$no_proxy"

echo "[k8s_agent] connecting to MACP at ${MACP_SERVER}"

exec uv run \
  --with websockets \
  --with kubernetes \
  --with anthropic \
  python "$SCRIPT_DIR/k8s_agent_wrapper.py" \
  --server "$MACP_SERVER"
