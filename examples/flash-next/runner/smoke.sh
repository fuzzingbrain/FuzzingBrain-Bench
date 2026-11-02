#!/usr/bin/env bash
# Validate the model id and native OpenAI tool-call parsing before a full run.
set -euo pipefail

BASE_URL=${FLASHNEXT_BASE_URL:-http://localhost:8000/v1}
MODEL=qwen3.8-flash-next:fp8

curl --silent --show-error --fail "$BASE_URL/models" | grep -q "\"$MODEL\""

response=$(curl --silent --show-error --fail "$BASE_URL/chat/completions" \
  -H 'Content-Type: application/json' \
  -d "{
    \"model\": \"$MODEL\",
    \"messages\": [{\"role\": \"user\", \"content\": \"Call echo_text with value ok.\"}],
    \"tools\": [{
      \"type\": \"function\",
      \"function\": {
        \"name\": \"echo_text\",
        \"description\": \"Return the supplied text\",
        \"parameters\": {
          \"type\": \"object\",
          \"properties\": {\"value\": {\"type\": \"string\"}},
          \"required\": [\"value\"]
        }
      }
    }],
    \"tool_choice\": \"required\",
    \"temperature\": 1.0,
    \"top_p\": 0.95,
    \"top_k\": 20,
    \"max_tokens\": 256
  }")

python3 -c 'import json,sys; x=json.load(sys.stdin); c=x["choices"][0]; assert c["message"].get("tool_calls"), x; print("Flash-Next endpoint and tool calls: OK")' <<<"$response"
