"""Claude-Code-CLI arm: drive headless `claude -p` over the bench MCP server.

Driven through the single unified entry (no standalone CLI):
  fb-bench run <bugs> --arm claudecode [--model sonnet] [--auth sub|api] [-o NAME]

orchestrator.run_matrix calls run_cell() per (bug x sample) cell, reusing the
same matrix machinery (resume / parallel / aggregate / report) as every arm.

The sibling of the Codex arm (fbbench/sweep/codex.py). It reuses the SAME bench
MCP server (the public canonical challenge image: `docker run -i --rm <image>
mcp-server`), the SAME neutral discovery view, the SAME netns-isolated exec(),
and grades through the SAME in-image harness — so the only difference between the
two product-CLI arms is the model/driver.

Cheat hardening (audited empirically — see the module docstring notes below):
Claude Code runs HEADLESS on the host, but EVERY host-side cheat surface is shut
off, not just forbidden by the prompt:
  - cwd is the bind-mounted ISOLATED workspace (a temp dir), NOT the repo — so
    the repo's `output/` (prior winning PoCs) and `bugs/` (the staged answer) are
    not reachable by relative path.
  - ALL built-in tools (Bash/Read/Write/Web*/Task/Skill/SlashCommand/…) are
    disallowed; the ONLY allowed tools are the `mcp__bench__*` ones named by
    BENCH_TOOL_NAMES, the same set every other arm gets. Verified
    that with these flags an agent explicitly instructed to shell out / read the
    host answer file produces ZERO non-bench tool calls and cannot reach it.
  - `--strict-mcp-config` → only the bench MCP server (no user MCP servers leak).
  - `--setting-sources project` with cwd = the empty workspace → the user's
    global allow-list / `skipDangerousModePermissionPrompt` do NOT apply.
  - the child env is scrubbed to PATH+HOME only (HOME kept for `claude` auth),
    mirroring Codex's `inherit = "none"`.
The one residual cheat surface — the in-container `mcp__bench__exec` reading the
answer key — is SHARED with the Codex arm (a bench-level issue), not a
Claude-specific regression.
"""
from __future__ import annotations

import json
import os
import shutil
import signal
import subprocess
import sys
import tempfile
import threading
import time
from pathlib import Path

from fbbench.grading import find_bug
from fbbench.prompts import (  # noqa: F401
    CODEX_TASK_PROMPT, budget_note, system_prompt)
from fbbench.runner.mcp_client import _full_scan_alias
# Reuse the Codex arm's host-side helpers verbatim so the two arms grade and
# select PoCs identically (same in-image grader, same blob heuristic).
from fbbench.sweep.codex import (
    IMAGE_PREFIX,
    _crash_signatures, _candidate_blobs,
)

MAX_TURNS_DEFAULT = 100
MODEL_DEFAULT = "sonnet"
MAX_RESUMES = 30  # parity with the Codex arm's resume cap

from fbbench.images import agent_image, image_digest
from fbbench.sweep.mcp_episode import BENCH_TOOL_NAMES, agent_tools_note

# The only tools the agent may call: the bench MCP tools, named from the one
# list every arm shares. Everything else is a host-side cheat/contamination
# surface and is hard-denied below.
_BENCH_TOOLS = ",".join(f"mcp__bench__{t}" for t in BENCH_TOOL_NAMES)
# Exhaustive built-in denylist. `--allowedTools` is NOT exclusive (tools absent
# from it can still run if they don't require a prompt — Skill/SlashCommand slip
# through), so we ALSO name every built-in here. Audited: with this list an agent
# told to shell out makes zero non-bench calls.
_DENY_TOOLS = ",".join((
    "Bash", "BashOutput", "KillShell", "Read", "Write", "Edit", "MultiEdit",
    "NotebookEdit", "Glob", "Grep", "Task", "Agent", "WebFetch", "WebSearch",
    "ToolSearch", "TodoWrite", "Skill", "SlashCommand", "ExitPlanMode",
))


def claude_task_prompt() -> str:
    """The BENCH's task prompt -- the same text the api arm is given.

    One brief for every arm. Every arm drives the same three tools, so there is
    nothing for a second prompt to express, and the api arm is the baseline
    everything is measured against -- its text is the one that wins.

    The only substitution is mechanical and forced: Claude Code namespaces MCP
    tools, so `setup()` is `mcp__bench__setup()` to it and nowhere else.
    """
    # The note is substituted too: it names run_poc_on_harness(), and a prompt
    # that says mcp__bench__run_poc_on_harness() everywhere else and the bare
    # name here would be pointing this arm at a tool it cannot call.
    p = system_prompt() + agent_tools_note()
    for tool in BENCH_TOOL_NAMES:
        p = p.replace(f"{tool}()", f"mcp__bench__{tool}()")
    return p


# No search strategy is prescribed to one arm and not the others: that is
# coaching, not a budget. An arm is told only the two facts it cannot count for
# itself -- turns and time -- by budget_note(), which every arm shares.


def model_label(model: str) -> str:
    """Result-dir label for this arm + model (e.g. claude-code-sonnet)."""
    return f"claude-code-{model}"



# --- one bench MCP server per EPISODE -----------------------------------------
# `claude -p` spawns its MCP servers per session, and the arm resumes a session
# up to MAX_RESUMES times, and all resumes share ONE mcp-server.
# The image keeps its crash-signature memory in that process, so every resume
# reset it and the agent was told "new" for crashes it had already found
# (observed: 4 crashes, all reported new, episode counter stuck at 1).
#
# Keep ONE server process for the whole episode and hand each claude session a
# relay that connects to it over a unix socket. Sessions are sequential, so the
# relay serves one client at a time.
# The per-episode MCP server and its stdio<->socket relay now live in
# mcp_episode.py, so the external arm serves the SAME tools from the SAME
# server instead of a parallel implementation.
from fbbench.sweep.mcp_episode import (  # noqa: F401
    _RELAY_SRC, AGENT_USD_CAP, AGENT_WALL_CAP_S, CandidateLog,
    _start_episode_server)  # noqa: E402,F401


def stage_claude_env(
    real_bug_dir: str, model: str, cell_dir=None, preserve_pocs: bool = True
) -> tuple[str, str, str, str, tuple]:
    """Stage an isolated workspace + a bench MCP config for the canonical image.

    Returns (image, root, work, mcp_cfg, (server, srv_sock)):
      - image:   docker.io/...-<alias> canonical challenge image
      - root:    cell temp dir (caller cleans it up)
      - work:    bind-mounted workspace (-> container /workspace) AND the claude
                 cwd — named by the NEUTRAL alias so the path leaks nothing.
      - mcp_cfg: path to bench.mcp.json wiring `docker run … mcp-server`.
      - server, srv_sock: the per-episode relay. THE CALLER OWNS THESE — close
                 the socket and terminate the process, or the run leaks a
                 subprocess and a listening port per cell.
    """
    alias = _full_scan_alias(real_bug_dir)
    image = agent_image(alias)   # same set the external arm runs in
    root = tempfile.mkdtemp(prefix=f"cc-{alias}-")
    work = os.path.join(root, "workspace")
    os.makedirs(work, exist_ok=True)
    os.chmod(work, 0o777)  # the container (root) writes candidate inputs here
    # One server for the whole episode; every claude session reaches it through
    # the relay, so the image's crash-signature memory survives a resume.
    # Watch the relay, so this arm keeps its candidates as it grades them
    # instead of only sweeping the workspace afterwards. Same observer the
    # external arm uses -- one implementation, so the two cannot drift.
    candidates = CandidateLog(cell_dir, work, preserve=preserve_pocs)
    server, sock_path, relay_path, srv_sock = _start_episode_server(
        image, work, root, candidates)
    mcp_cfg = os.path.join(root, "bench.mcp.json")
    with open(mcp_cfg, "w") as f:
        json.dump({"mcpServers": {"bench": {
            "command": sys.executable,
            "args": [relay_path, sock_path]}}}, f)
    return image, root, work, mcp_cfg, (server, srv_sock, candidates)


def claude_cmd(prompt: str, mcp_cfg: str, model: str, max_turns: int,
               resume_session: str | None = None) -> list[str]:
    """The hardened `claude -p` argv (see module docstring for the threat model)."""
    cmd = ["claude", "-p", prompt,
           "--output-format", "stream-json", "--verbose",
           "--model", model,
           "--mcp-config", mcp_cfg, "--strict-mcp-config",
           "--allowedTools", _BENCH_TOOLS,
           "--disallowedTools", _DENY_TOOLS,
           "--permission-mode", "default",
           "--setting-sources", "project",
           "--max-turns", str(max_turns)]
    if resume_session:
        cmd += ["--resume", resume_session]
    return cmd


def _anthropic_key() -> str | None:
    """The pay-as-you-go API key for --auth api, from ./.env then the environment."""
    from fbbench.env import read_dotenv
    return read_dotenv().get("ANTHROPIC_API_KEY") or os.environ.get("ANTHROPIC_API_KEY")


def _clean_env(auth: str = "sub", api_key: str | None = None,
               home: str | None = None) -> dict:
    """Env for the `claude` PARENT process (host-side). PATH+HOME only, mirroring
    Codex's `inherit = none`. The bench MCP `docker run` forwards no `-e`, so
    whatever is here NEVER reaches the container — the model key stays with the
    agent, exactly like the API arm (env key) and the Codex arm (auth.json).

    Two auth entries:
      - 'sub' (default, backward compatible): OAuth subscription. Real HOME holds
        ~/.claude creds and NO API key is set, so `claude` uses the claude.ai (Max)
        login. Subject to that plan's session limit.
      - 'api': API key. ANTHROPIC_API_KEY is set (it takes precedence over OAuth)
        and HOME points at an isolated dir with NO ~/.claude creds, so there is no
        OAuth/key conflict — pay-as-you-go, no session-limit throttle.
    """
    env = {"PATH": os.environ.get("PATH", "/usr/bin:/bin"),
           "HOME": home or os.environ.get("HOME", "")}
    if auth == "api":
        if not api_key:
            raise SystemExit("claudecode --auth api: no ANTHROPIC_API_KEY in "
                             "./.env or environment")
        env["ANTHROPIC_API_KEY"] = api_key
    return env


def _kill_pg(proc: subprocess.Popen) -> None:
    try:
        os.killpg(os.getpgid(proc.pid), signal.SIGKILL)
    except Exception:
        try:
            proc.kill()
        except Exception:
            pass



def _snapshot_graded(tool_input: dict, work: str, snap_dir: str, n: int) -> None:
    """Copy a just-submitted candidate out of the workspace before it can be
    overwritten. Best-effort: a missing file is not worth failing an episode."""
    p = str(tool_input.get("path") or "")
    if not p.startswith("/workspace/"):
        return
    src = os.path.join(work, p[len("/workspace/"):])
    try:
        os.makedirs(snap_dir, exist_ok=True)
        shutil.copy(src, os.path.join(snap_dir, f"g{n:03d}-{os.path.basename(src)}"))
    except OSError:
        pass


def _run_claude_once(argv: list[str], lf, deadline: float, work: str = "",
                     snap_dir: str = "", env: dict | None = None) -> dict:
    """Run ONE `claude -p` process, streaming stream-json lines to `lf` and
    parsing them live. A watchdog hard-kills on the wall-clock backstop.

    `env` selects the auth entry (PATH+HOME[+ANTHROPIC_API_KEY]); None inherits
    the parent env. Returns {turns, grade_calls, tokens, usd, session_id, ended}
    for THIS invocation, where a turn == one assistant MESSAGE (one model API
    call). NB: stream-json splits a multi-block message into several `assistant`
    events that SHARE a message.id, so we dedupe by id — matching `--max-turns`.
    """
    proc = subprocess.Popen(argv, stdin=subprocess.DEVNULL,
                            stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
                            text=True, bufsize=1, start_new_session=True, env=env)
    st = {"turns": 0, "grade_calls": 0, "tokens": 0, "usd_by_session": {},
          "input_tokens": 0, "output_tokens": 0,
          "cache_read_tokens": 0, "cache_write_tokens": 0,
          "session_id": None, "ended": "exited"}
    msg_ids: set = set()
    grade_ids: set = set()
    stop = threading.Event()

    def _watch():
        while not stop.wait(3):
            if time.time() > deadline:
                st["ended"] = "deadline"
                _kill_pg(proc)
                return
    wd = threading.Thread(target=_watch, daemon=True)
    wd.start()

    for line in proc.stdout:  # blocks until EOF (proc exit / killed)
        lf.write(line)
        line = line.strip()
        if not line:
            continue
        try:
            ev = json.loads(line)
        except Exception:
            continue
        t = ev.get("type")
        if t == "system" and ev.get("subtype") == "init":
            st["session_id"] = ev.get("session_id") or st["session_id"]
        elif t == "assistant":
            msg = ev.get("message", {})
            mid = msg.get("id")
            if mid is not None:
                msg_ids.add(mid)
            st["turns"] = len(msg_ids)
            for b in msg.get("content", []):
                if (b.get("type") == "tool_use"
                        and str(b.get("name", "")).endswith("__run_poc_on_harness")):
                    grade_ids.add(b.get("id"))
                    # Snapshot what was graded, NOW. Only the workspace's final
                    # contents are scored at the end, so an agent that reuses one
                    # filename (observed: /workspace/poc.bin graded 8 times in a
                    # single libpng-01 episode) silently loses every earlier
                    # version -- including a crashing one. The longer the budget,
                    # the more often this happens.
                    _snapshot_graded(b.get("input") or {}, work, snap_dir,
                                     len(grade_ids))
            st["grade_calls"] = len(grade_ids)
        elif t == "result":
            st["session_id"] = ev.get("session_id") or st["session_id"]
            u = ev.get("usage") or {}
            it = int(u.get("input_tokens", 0))
            ot = int(u.get("output_tokens", 0))
            st["input_tokens"] += it
            st["output_tokens"] += ot
            st["cache_read_tokens"] += int(u.get("cache_read_input_tokens", 0))
            st["cache_write_tokens"] += int(u.get("cache_creation_input_tokens", 0))
            st["tokens"] += it + ot
            # total_cost_usd is the SESSION's running total, not this turn's
            # cost. Keyed by session and overwritten, never summed -- see the
            # note above the accumulator in run_once().
            sid = ev.get("session_id") or st["session_id"]
            st["usd_by_session"][sid] = float(ev.get("total_cost_usd") or 0.0)
        elif t == "system" and ev.get("subtype") == "api_retry":
            # 401/403 can never be fixed by retrying or resuming; a whole run
            # would otherwise spend the wall clock retrying and record a false zero.
            if str(ev.get("error_status")) in ("401", "403"):
                st["ended"] = "auth_error"
    try:
        proc.wait(timeout=10)
    except Exception:
        _kill_pg(proc)
    stop.set()
    return st


def run_claude(work: str, mcp_cfg: str, model: str, timeout_s: int,
               max_turns: int = MAX_TURNS_DEFAULT, *,
               auth: str = "sub", api_key: str | None = None) -> dict:
    """Drive `claude -p` to a fixed TURN budget, EB-style (like the Codex arm).

    A turn = one model API call (one `assistant` event). Claude satisfices before
    the budget, so after each process exits we RESUME the session (`--resume`)
    with the same EB nudge (wrap-up / stuck-grade / continue) until the budget is
    hit. Each resume's per-invocation `--max-turns` is the REMAINING budget so a
    single process can never overshoot. Wall-clock `timeout_s` is an anti-hang
    backstop only.

    `auth` picks the auth entry ('sub' = OAuth Max, 'api' = ANTHROPIC_API_KEY).
    For 'api' we stage an isolated HOME (no ~/.claude creds) so the key is used
    cleanly with no OAuth conflict; both entries keep the key out of the container.
    """
    if auth == "api":
        home = os.path.join(os.path.dirname(work), "claude_home")
        os.makedirs(home, exist_ok=True)
    else:
        home = None
    env = _clean_env(auth, api_key, home)

    log_path = os.path.join(work, "claude.log")
    snap_dir = os.path.join(os.path.dirname(work), "graded")
    t0 = time.time()
    # Same ceiling every agent arm gets: a black box the bench cannot count
    # tokens inside needs a hard stop on both axes. See external.AGENT_*_CAP.
    deadline = t0 + min(timeout_s, AGENT_WALL_CAP_S)
    turns = grade_calls = tokens = 0
    in_tok = out_tok = cr_tok = cw_tok = 0
    # total_cost_usd is the cost of the SESSION so far, and a resume reports
    # the whole figure again. Keyed by session id and overwritten, never summed:
    # adding them compounds, and the inflated total would trip the agent cost
    # cap and end a run for money it had not spent.
    cost_by_session: dict = {}
    usd = 0.0
    session_id = None
    last_grade_turn = 0
    terminated = "resumes_exhausted"

    with open(log_path, "w") as lf:
        prompt = claude_task_prompt()
        resume = None
        for attempt in range(MAX_RESUMES + 1):
            remaining = max_turns - turns
            if remaining <= 0:
                terminated = "turn_budget"
                break
            argv = claude_cmd(prompt, mcp_cfg, model, remaining, resume_session=resume)
            st = _run_claude_once(argv, lf, deadline, work, snap_dir, env)
            turns += st["turns"]
            grade_calls += st["grade_calls"]
            tokens += st["tokens"]
            in_tok += st["input_tokens"]
            out_tok += st["output_tokens"]
            cr_tok += st["cache_read_tokens"]
            cw_tok += st["cache_write_tokens"]
            cost_by_session.update(st["usd_by_session"])
            usd = sum(cost_by_session.values())
            if st["grade_calls"]:
                last_grade_turn = turns
            session_id = st["session_id"] or session_id

            if st.get("ended") == "auth_error":
                terminated = "auth_error"
                break
            if turns >= max_turns:
                terminated = "turn_budget"
                break
            if usd >= AGENT_USD_CAP:
                terminated = "cost-cap"
                break
            if st["ended"] == "deadline" or time.time() > deadline:
                terminated = "timeout"
                break
            if attempt >= MAX_RESUMES or not session_id:
                terminated = "resumes_exhausted"
                break
            # Claude stopped on its own with budget left → nudge and resume.
            # The same line the api arm gets between turns: where the budget
            # stands, and nothing about what to do with it.
            nudge = budget_note(turns, max_turns, max_turns - turns,
                                elapsed_s=time.time() - t0,
                                remaining_s=max(0.0, deadline - time.time()),
                                time_budget_s=float(timeout_s))
            lf.write(json.dumps({"fbbench_nudge": nudge, "at_turn": turns}) + "\n")
            prompt = nudge
            resume = session_id

    return {"terminated": terminated, "duration_s": time.time() - t0,
            "log_path": log_path, "snap_dir": snap_dir, "turns": turns, "grade_calls": grade_calls,
            "tokens": tokens, "input_tokens": in_tok, "output_tokens": out_tok,
            "cache_read_tokens": cr_tok, "cache_write_tokens": cw_tok,
            "total_usd": round(usd, 4)}


def _stream_to_transcript(log_path: str, out_path: Path, *, model: str,
                          bug_id: str) -> None:
    """Convert a claude stream-json log into report.py's transcript.jsonl format.

    Maps assistant text + tool_use → assistant events, tool_result (in `user`
    events) → tool_result events, and our resume nudges → budget_note events, so
    report.py renders Claude episodes exactly like the API / Codex arms.
    """
    events: list[dict] = [{
        "event": "start", "model": model, "bug_id": bug_id,
        "system_prompt": claude_task_prompt(),
        "initial_user_message": "",
    }]
    call_name: dict[str, str] = {}
    call_input: dict[str, object] = {}
    turn = 0
    # stream-json splits one assistant message across several events sharing a
    # message.id; coalesce them so each model turn is ONE transcript event.
    seen_msg: dict[str, int] = {}   # message.id -> index in `events`
    seen_block: set = set()         # (mid, block-key) to avoid double-adding
    for raw in open(log_path, errors="ignore"):
        raw = raw.strip()
        if not raw:
            continue
        try:
            ev = json.loads(raw)
        except Exception:
            continue
        if "fbbench_nudge" in ev:
            events.append({"event": "budget_note", "turn": turn,
                           "note": ev["fbbench_nudge"]})
            continue
        t = ev.get("type")
        if t == "assistant":
            msg = ev.get("message", {})
            mid = msg.get("id") or f"_anon{len(events)}"
            if mid not in seen_msg:
                turn += 1
                events.append({
                    "event": "assistant", "turn": turn, "text": "",
                    "stop_reason": "end_turn",
                    "input_tokens": 0, "output_tokens": 0,
                    "cache_read_tokens": 0, "cache_write_tokens": 0,
                    "tool_calls": [],
                })
                seen_msg[mid] = len(events) - 1
            ae = events[seen_msg[mid]]
            for b in msg.get("content", []):
                if b.get("type") == "text":
                    key = (mid, "t", b.get("text", "")[:40])
                    if key in seen_block:
                        continue
                    seen_block.add(key)
                    ae["text"] = (ae["text"] + "\n\n" + b.get("text", "")).strip()
                elif b.get("type") == "tool_use":
                    cid = b.get("id") or ""
                    if (mid, cid) in seen_block:
                        continue
                    seen_block.add((mid, cid))
                    name = str(b.get("name", "")).split("__")[-1]
                    call_name[cid] = name
                    call_input[cid] = b.get("input")
                    ae["tool_calls"].append(
                        {"id": cid, "name": name, "input": b.get("input")})
                    ae["stop_reason"] = "tool_use"
        elif t == "user":
            for b in ev.get("message", {}).get("content", []):
                if b.get("type") != "tool_result":
                    continue
                cid = b.get("tool_use_id") or ""
                out = b.get("content")
                result = out
                if isinstance(out, list):
                    result = "\n".join(
                        x.get("text", "") for x in out if isinstance(x, dict))
                if isinstance(result, str):
                    try:
                        result = json.loads(result)
                    except Exception:
                        pass
                events.append({
                    "event": "tool_result", "id": cid,
                    "tool": call_name.get(cid, "?"), "result": result,
                    "is_error": bool(b.get("is_error")),
                    "input": call_input.get(cid),
                })
    with open(out_path, "w") as f:
        for e in events:
            f.write(json.dumps(e, ensure_ascii=False) + "\n")



def _usage_floor(log_path: str) -> dict:
    """Per-message token totals from a stream log, as a FLOOR.

    Claude Code reports authoritative usage (thinking tokens included) only in
    its `result` event; a session killed by the wall clock emits none, which is
    how a 30-minute episode recorded $0.00. Summing the per-message usage
    recovers a lower bound — it misses thinking tokens, so label it as a floor
    rather than passing it off as the real figure.
    """
    seen: set[str] = set()
    t = {"input_tokens": 0, "output_tokens": 0,
         "cache_read_tokens": 0, "cache_write_tokens": 0}
    try:
        fh = open(log_path, errors="ignore")
    except OSError:
        return t
    with fh:
        for line in fh:
            try:
                ev = json.loads(line)
            except ValueError:
                continue
            msg = ev.get("message") or {}
            u, mid = msg.get("usage"), msg.get("id")
            if not u or not mid or mid in seen:
                continue
            seen.add(mid)
            t["input_tokens"] += int(u.get("input_tokens", 0))
            t["output_tokens"] += int(u.get("output_tokens", 0))
            t["cache_read_tokens"] += int(u.get("cache_read_input_tokens", 0))
            t["cache_write_tokens"] += int(u.get("cache_creation_input_tokens", 0))
    return t

def _graded_paths(log_path: str, work: str) -> list[str]:
    """Workspace files the agent explicitly ran through the harness.

    _candidate_blobs() filters by extension (.json/.txt/... are treated as
    scaffolding), which silently drops a PoC for any target whose input format
    IS json or text. Anything the agent graded during the episode is a candidate
    by definition, so add those back.
    """
    out: list[str] = []
    try:
        fh = open(log_path, errors="ignore")
    except OSError:
        return out
    with fh:
        for line in fh:
            try:
                ev = json.loads(line)
            except ValueError:
                continue
            for b in ((ev.get("message") or {}).get("content") or []):
                if (isinstance(b, dict) and b.get("type") == "tool_use"
                        and str(b.get("name", "")).endswith("run_poc_on_harness")):
                    p = (b.get("input") or {}).get("path") or ""
                    if p.startswith("/workspace/"):
                        local = os.path.join(work, p[len("/workspace/"):])
                        if os.path.isfile(local):
                            out.append(local)
    return out


def _persist(cell_dir: Path, *, bug: str, model: str, real: str,
             r: dict, blobs: list[str], alias: str, preserve_pocs: bool = True,
             fuzzing_attempts: int = 0) -> dict:
    """Re-grade blobs in the challenge image, write score.json + report.
    With preserve_pocs, every graded candidate is kept under pocs/{crashed,clean}/
    (same forensic record as the API arm)."""
    cell_dir.mkdir(parents=True, exist_ok=True)
    sigs, best_blob = _crash_signatures(
        Path(real), blobs, pocs_dir=str(cell_dir / "pocs") if preserve_pocs else None)
    if best_blob:
        shutil.copy(best_blob, cell_dir / "best_blob")
    if Path(r["log_path"]).is_file():
        shutil.copy(r["log_path"], cell_dir / "claude.log")
    score = {
        "bug_id": bug, "model": model_label(model), "seed": 0,
        # Scored on distinct crash signatures, the same unit the API arm reports.
        "fuzzing_attempts": fuzzing_attempts,
        "agent_image": agent_image(alias),
        "agent_image_digest": image_digest(agent_image(alias)),
        "unique_crashes": len(sigs), "crash_signatures": sorted(sigs),
        "score": len(sigs), "grading": "in-image",
        "terminated_reason": r["terminated"], "turns_used": r["turns"],
        "max_turns": r.get("max_turns"), "duration_s": round(r["duration_s"], 1),
        "grade_calls": r["grade_calls"], "blobs_written": len(blobs),
        "tokens_used": r["tokens"] or None, "total_usd": r["total_usd"],
    }
    (cell_dir / "score.json").write_text(json.dumps(score, indent=2))
    # cost.json, aligned with the api/codex arms. total_usd is Claude Code's OWN
    # reported cost (total_cost_usd), not derived from our catalog, so it is the
    # authoritative number; the token breakdown comes from its usage events.
    from fbbench.models import cost_report
    toks = {k: r.get(k, 0) for k in ("input_tokens", "output_tokens",
                                     "cache_read_tokens", "cache_write_tokens")}
    basis = "authoritative"
    if not any(toks.values()):
        # Killed session: no result event, so fall back to a per-message floor,
        # which omits thinking tokens and is therefore a lower bound.
        toks = _usage_floor(r["log_path"])
        basis = "floor"
    cost = cost_report(model, basis=basis, **toks)
    cost["model"] = model_label(model)
    cost["vendor_reported_usd"] = r["total_usd"] or None   # cross-check only
    (cell_dir / "cost.json").write_text(json.dumps(cost, indent=2))
    try:
        _stream_to_transcript(r["log_path"], cell_dir / "transcript.jsonl",
                              model=model_label(model), bug_id=bug)
        from fbbench.runner.report import write_report
        write_report(cell_dir)
    except Exception as e:  # noqa: BLE001
        print(f"report skipped: {e}")
    return score


def run_cell(cell_dir: Path, bug: str, model: str, timeout_s: int,
             max_turns: int = MAX_TURNS_DEFAULT, *,
             auth: str = "sub", api_key: str | None = None,
             preserve_pocs: bool = True) -> dict | None:
    """Run one Claude-Code episode into an explicit cell_dir and write score.json.

    The per-cell contract the matrix engine drives for every arm; resume is the
    caller's job (run_matrix skips a cell whose score.json already exists)."""
    cell_dir = Path(cell_dir)
    real = find_bug(bug)
    if not real:
        return {"error": f"bug not found: {bug}"}
    alias = _full_scan_alias(str(real))
    _image, root, work, mcp_cfg, (server, srv_sock, candidates) = stage_claude_env(
        str(real), model, cell_dir=cell_dir, preserve_pocs=preserve_pocs)
    try:
        r = run_claude(work, mcp_cfg, model, timeout_s, max_turns,
                       auth=auth, api_key=api_key)
        r["max_turns"] = max_turns
        # What the agent actually ran through run_poc_on_harness, seen live on
        # the relay. The workspace sweep and the log scrape are kept as a
        # fallback for a transcript the observer never saw (a resumed session).
        candidates.close()
        blobs = sorted(set(candidates.host_blobs()
                           + _candidate_blobs(work)
                           + _graded_paths(r["log_path"], work)
                           + _candidate_blobs(r.get("snap_dir", ""))))
        score = _persist(cell_dir, bug=bug, model=model, real=str(real),
                         r=r, blobs=blobs, alias=alias, fuzzing_attempts=len(candidates.blocked), preserve_pocs=preserve_pocs)
    finally:
        for closer in (srv_sock.close, server.terminate):
            try:
                closer()
            except Exception:  # noqa: BLE001
                pass
        try:
            server.wait(timeout=5)
        except Exception:  # noqa: BLE001
            _kill_pg(server)
        shutil.rmtree(root, ignore_errors=True)
    return score


# The Claude-Code arm has no standalone CLI: it is driven through the single
# unified entry `fb-bench run <bugs> --arm claudecode [--auth sub|api]`, which
# calls run_cell() per matrix cell (resume / parallel / aggregate / report all
# reused from orchestrator.run_matrix).


if __name__ == "__main__":
    # Redirect the old `python -m fbbench.sweep.claudecode ...` entry to the
    # unified CLI instead of silently doing nothing.
    import sys
    sys.exit("the Claude-Code arm has no standalone CLI.\n"
             "use:  fb-bench run <bugs> --arm claudecode [--model sonnet] [--auth sub|api]")
