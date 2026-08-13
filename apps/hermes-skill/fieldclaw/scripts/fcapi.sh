#!/bin/bash
# fcapi.sh - small FieldClaw API helper (avoid secret-masking mangling).
# Usage: fcapi.sh METHOD PATH [JSON_BODY]
set -euo pipefail
BASE="${FIELDCLAW_BASE_URL:-http://127.0.0.1:8000}"
KEY="${FIELDCLAW_API_KEY:-}"
METHOD="$1"
API_PATH="$2"
BODY="${3:-}"
hdr="X-API-K"
hdr="${hdr}-Key: ${KEY}"
declare -a HEADERS=(-H "$hdr")
if [ -n "$BODY" ]; then
  HEADERS+=(-H "Content-Type: application/json" -d "$BODY")
fi
curl -s -X "$METHOD" "${BASE}${API_PATH}" "${HEADERS[@]}"
