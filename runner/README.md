# FuzzingBrain Bench runner

Drives one episode = one `(model, bug, seed)` cell. Speaks to the
`tools/mcp-server/` Go binary over stdio; uses the Anthropic Python SDK
for the model loop.

## Setup

```bash
# Build the MCP server
go -C tools/mcp-server build -o ../../bin/mcp-server

# Install runner deps
pip install -r runner/requirements.txt

# Export API key
export ANTHROPIC_API_KEY=...
```

## Run one episode

```bash
python -m runner \
  --bug netsnmp-vacm-parse-npd \
  --model claude-opus-4-7 \
  --seed 0 \
  --max-turns 60 \
  --output runs/
```

Produces under `runs/<bug>/<model>/seed-<n>/`:

- `episode.jsonl` — turn-by-turn trace (assistant text + tool calls + tool results)
- `score.json` — final capability bitmap + tier score (0..4)
- `cost.json` — input/output token usage

## Three-seed scoring

Per SPEC §6.3, the headline number for a `(model, bug)` cell is the
best-of-three union across seeds. Run three seeds, then aggregate
externally — the runner intentionally writes per-seed files.

## What the runner does NOT do (v1)

- No multi-process parallelism across bugs (run them with `xargs -P`).
- No coaching / Stuck-nudges (v2 adaptive arm).
- No vendor-CLI shim (out of v1 scope).
- No Docker isolation — the MCP server is a host subprocess. This means
  agent `exec` commands run as the runner's UID. Run on a throwaway VM.
