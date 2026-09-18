# Running an external agent

The bench can evaluate an agent it does not contain. The agent lives in its own
repository; the bench is handed a short manifest that says how to invoke it, and
nothing else about it enters this tree.

```bash
fb-bench run <bugs> --agent <name-or-path>
```

## The contract

Every agent arm — `claudecode`, `codex` and any external agent — plugs into the
same waist, and that is the point of v2. An arm is a different agent driving
**identical tools**, not a different set of tools.

1. The bench starts one **bench MCP server** for the episode, inside the sealed
   challenge image, and exposes it on a unix socket.
2. The agent speaks MCP to it. `relay.py` is a stdio↔socket shim, so an agent
   that already talks MCP over stdin/stdout needs to know nothing about sockets.
3. Everything the agent does to the challenge goes through that server's tools.

What the agent sees, identical on every arm:

| | |
|---|---|
| working directory | `/challenge` — **read-only** |
| writable | `/workspace` (bind-mounted out to the bench) and `/tmp` |
| the source | `/challenge/src`, the harness under `/challenge/harness` |
| the oracle | `run_poc_on_harness(path)` — raw harness stdout/stderr, crash novelty, per-round detail |
| network | none |
| debugger | `gdb`, where the challenge image ships one |

The agent never touches Docker, never learns the image name, and never learns
which version it is looking at — the source it reads and the harness its
candidate runs on are the one sealed image, so they cannot disagree. Scoring is
the bench's own `grade_blob`, the same number every arm reports.

> **v1 → v2.** There used to be a staged host-side copy of the challenge, a
> `./submit` script writing into a request directory, and a `./reach` responder
> that shelled out to gdb in a throwaway container. All three are gone: they
> gave the external arm a *different* surface, which is exactly the asymmetry v2
> removes. An external agent must now speak MCP; the "any agent with a bare
> shell" property is the price of tool parity. **v1 and v2 results are not
> comparable.**

## The manifest

```yaml
name: fbagent

# How the bench invokes the agent.
# Template fields: {mcp_socket} {relay} {opening} {timeout} {max_turns} {model}
# @path inlines a file next to the manifest (e.g. a long system prompt).
command: >
  my-agent --mcp-relay {relay} --mcp-socket {mcp_socket}
  -p "{opening}" --max-turns {max_turns} --max-time {timeout} --model {model}

# blocked (default) or allowed. The challenge container has no network either
# way; this governs the agent process itself.
network: blocked
```

The same two values are also in the environment, for a manifest that would
rather read them there: `FBBENCH_MCP_SOCKET` and `FBBENCH_MCP_RELAY`.

`shell_env` is still parsed so an old manifest loads, and ignored — v2 has no
host-side shell to point at a sandbox.

### Fields

| field | what it is |
|---|---|
| `{mcp_socket}` | unix socket for this episode's bench MCP server |
| `{relay}` | path to `relay.py`, a stdio↔socket shim |
| `{opening}` | the task prompt — **the bench's own, byte-identical to every other arm's** |
| `{timeout}` | wall-clock seconds; the bench enforces this on the second |
| `{max_turns}` | the turn budget, which the agent must honour and report |
| `{model}` | the model id, the same string the other arms are given |

## Budget

Every arm gets a turn cap and a hard wall clock, and **no dollar cap**. The api
arm owns its loop and bounds it directly; the CLI arms are handed `{max_turns}`
and trusted to obey. An external agent is the same shape — a black box whose
model calls the bench cannot count — so it gets the same contract, and
`turn_budget_honoured` in `score.json` records whether it kept it.

## Registering a name

`--agent` takes a path or a bare name. A name is looked up as
`<name>.agent.yaml` on a search path, in order:

1. `$FBBENCH_AGENTS` (colon-separated directories)
2. `~/.config/fbbench/agents/`
3. `agents/` in this repository

```bash
ln -s /path/to/agent-repo/my-agent.agent.yaml ~/.config/fbbench/agents/my-agent.agent.yaml
fb-bench run all --agent my-agent --jobs 4
```

Nothing about the agent is copied into the bench. The pointer is all it holds.

## What a run leaves

```
output/<run>/<bug>/<model>/seed-0/
├── score.json      unique_crashes, crash_signatures, duration, network, agent
├── best_blob       the first candidate that crashed
├── agent.log       the agent's transcript
├── progress.jsonl  one flushed line per candidate, as it is graded
└── pocs/{crashed,clean}/   every candidate it submitted, with its verdict
```

`progress.jsonl` and `pocs/` are written **live**, by watching the agent's own
`run_poc_on_harness` calls on the relay. Two consequences worth knowing:

- An interrupted or killed episode still leaves everything it spent. That is
  not a nicety — a terminated run once lost 236 graded candidates and its cost.
- What is recorded is what the agent **submitted**, not what it left in the
  workspace. Grading a workspace sweep charges three in-image rounds to run the
  agent's `gen.py` through the harness and calls the result a PoC.

`score.json` records `agent` and `grading: in-image` — who ran (an external
agent) and who judged (the bench), kept apart so the number can be trusted.

## Reporting cost (optional)

The bench cannot see inside an external agent, so a run's cost is only knowable
if the agent reports it. Write `.fbbench/usage.json` in the workspace before
exiting:

```json
{
  "model": "claude-opus-5",
  "input_tokens": 35217,
  "output_tokens": 6376,
  "cache_read_tokens": 537296,
  "cache_write_tokens": 29186,
  "input_is_total": false
}
```

Set `input_is_total: true` if `input_tokens` includes the cached prefix (what
OpenAI-style clients report); the bench de-totals it so every arm prices the
same way. The cost is then computed with the bench's own price table and
recorded with `cost_basis: agent-reported`.

An agent that reports nothing is costed as **unknown**, not as zero — `total_usd`
stays null and the leaderboard prints `$ —`. A missing cost must never look like
a free run.
