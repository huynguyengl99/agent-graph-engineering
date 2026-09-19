#!/bin/bash
# Generate the backend's Python WebSocket client from the agent's AsyncAPI document.
#
# The agent service must be running. Its AsyncAPI document is the contract:
# change a message in triage/ws/messages.py, restart the agent, re-run this,
# and the backend's client follows.

set -euo pipefail

AGENT_URL="${AGENT_URL:-http://localhost:8001}"
SCHEMA_URL="${AGENT_URL}/asyncapi.json"
OUTPUT_DIR="$(cd "$(dirname "$0")/.." && pwd)/backend/helpdesk/agent_client"

echo "🔧 Generating agent WebSocket client for the backend..."
echo "   Schema: ${SCHEMA_URL}"

if ! curl -sf -o /dev/null "${SCHEMA_URL}"; then
  echo "❌ Cannot reach ${SCHEMA_URL}. Start the agent first: just agent" >&2
  exit 1
fi

cd "$(dirname "$0")/../agent"
uv run chanx generate-client \
  --schema "${SCHEMA_URL}" \
  --output "${OUTPUT_DIR}" \
  --clear-output

echo "✅ Agent client generated at backend/helpdesk/agent_client/"
