"""Codex-CLI arm: drive `codex exec` over the bench MCP server.

Driven through the single unified entry (no standalone CLI):
  fb-bench run <bugs> --arm codex [--model gpt-5.5] [--auth api|sub] [-o NAME]

The same bench as the Claude Code arm with a different agent. Everything the
bench controls is shared with sweep.claudecode, not reimplemented:
  - the image: agent_image(<alias>), with gdb/jdb and the call graph;
  - one mcp-server per episode (mcp_episode._start_episode_server), reached
    through the same relay, observed by the same CandidateLog, so every graded
    candidate is kept as it is graded;
  - the environment probe, the gdb source map and the toolbox line;
  - the brief: the api arm's system prompt (as developer instructions, appended
    to Codex's own the way --append-system-prompt appends to Claude Code's) and
    its first user turn, with the one substitution the MCP namespace forces;
  - the budget: AGENT_WALL_CAP_S and AGENT_USD_CAP per challenge, the turn
    budget, budget_note() between sessions, and the end the agent may call
    itself (ASSESSMENT COMPLETE);
  - grading in the image the episode ran in, and the score.json fields.
Codex's own host-side tools (shell, web, browser, apps, images, sub-agents) are
switched off in config.toml, as Claude Code's are by --disallowedTools.
"""
from __future__ import annotations

import glob
import json
import os
import re
import shutil
import signal
import subprocess
import sys
import tempfile
import threading
import time
from pathlib import Path

from fbbench.grading import find_bug, grade_blob
from fbbench.images import agent_image, image_digest
from fbbench.prompts import budget_note
from fbbench.runner.mcp_client import _full_scan_alias
from fbbench.sweep.mcp_episode import (
    AGENT_USD_CAP, AGENT_WALL_CAP_S, CandidateLog, _start_episode_server,
    debugger_offered, fetch_setup, install_gdb_source_map, probe_environment)

# The raw codex model id. `--arm codex --model X` picks X.
MODEL_DEFAULT = "gpt-5.5"
MAX_TURNS_DEFAULT = 100
# Not a budget, as in the Claude Code arm: high enough that the wall clock or
# the dollar cap is what stops a cell.
MAX_RESUMES = 400
# The published challenge images. No longer used by this arm (it runs in the
# agent image); kept because other modules import the name.
IMAGE_PREFIX = os.environ.get("FBBENCH_IMAGE_PREFIX", "docker.io/osanzas/fbbench-agent-")
# The MCP server's name in config.toml. Codex shows its tools to the model as
# mcp__bench__<tool>, the same names Claude Code gives them.
SERVER = "bench"


def model_label(model: str) -> str:
    """Cell/report label for a codex model, distinct from the api arm's raw id."""
    return f"codex-{model}"


def _is_grade_tool(name: str) -> bool:
    return (name or "").endswith("run_poc_on_harness")


# Every Codex feature that hands the model a tool of its own, off. What is left
# is the bench server's tools, as with Claude Code's --allowedTools.
_OFF_FEATURES = (
    "shell_tool", "unified_exec", "apps", "browser_use", "browser_use_external",
    "computer_use", "image_generation", "multi_agent", "plugins", "view_image",
    "sleep_tool", "goals", "code_mode_host", "tool_suggest", "skill_search",
)

_CODEX_CONFIG = """\
model = {model}
# Never switch login method silently when both credentials are present.
forced_login_method = {login}
web_search = "disabled"
# The api arm's system prompt, added after Codex's own instructions rather than
# replacing them -- the same thing --append-system-prompt does for Claude Code.
developer_instructions = {instructions}

[features]
{features}

[shell_environment_policy]
inherit = "none"
include_only = ["PATH"]

[history]
persistence = "none"

# The episode's one mcp-server, through the relay every agent arm uses.
[mcp_servers.{server}]
command = {python}
args = [{relay}, {sock}]
tool_timeout_sec = 300
startup_timeout_sec = 60
"""


def codex_config(*, model: str, login: str, instructions: str,
                 relay_path: str, sock_path: str) -> str:
    q = json.dumps   # a JSON string is a valid TOML basic string
    return _CODEX_CONFIG.format(
        model=q(model), login=q(login), instructions=q(instructions),
        features="\n".join(f"{f} = false" for f in _OFF_FEATURES),
        server=SERVER, python=q(sys.executable), relay=q(relay_path),
        sock=q(sock_path))


def codex_task_prompt(setup_resp: dict | None = None,
                      env_caps: dict | None = None) -> str:
    """The bench's first user turn -- exactly the text Claude Code is handed.
    Both CLIs namespace MCP tools as mcp__bench__<tool>, so it is the same
    function, not a copy."""
    from fbbench.sweep.claudecode import claude_task_prompt
    return claude_task_prompt(setup_resp, env_caps)


def stage_codex_env(real_bug_dir: str, model: str = MODEL_DEFAULT,
                    login: str = "api", cell_dir=None,
                    preserve_pocs: bool = True) -> tuple:
    """Stage the episode: the agent image's mcp-server, a workspace, CODEX_HOME.

    Returns (image, root, work, codex_home, (server, srv_sock, candidates,
    setup_resp, env_caps)). THE CALLER OWNS server and srv_sock, as in
    claudecode.stage_claude_env.
    """
    alias = _full_scan_alias(real_bug_dir)
    image = agent_image(alias)   # the same image the other agent arms run in
    root = tempfile.mkdtemp(prefix=f"codex-{alias}-")
    work = os.path.join(root, "workspace")
    os.makedirs(work, exist_ok=True)
    os.chmod(work, 0o777)  # the container (root) writes candidate inputs here
    candidates = CandidateLog(cell_dir, work, preserve=preserve_pocs)
    server, sock_path, relay_path, srv_sock = _start_episode_server(
        image, work, root, candidates)
    setup_resp = fetch_setup(sock_path)
    env_caps = probe_environment(sock_path)
    if env_caps.get("gdb"):
        env_caps["gdb_source_map"] = install_gdb_source_map(
            sock_path, env_caps.get("target", ""))
    from fbbench.sweep.external import agent_system_prompt
    codex_home = os.path.join(root, "codex_home")
    os.makedirs(codex_home, exist_ok=True)
    # The ChatGPT sign-in only for --auth sub; codex_home is outside the
    # workspace, so it never reaches the container.
    auth = os.path.expanduser("~/.codex/auth.json")
    if login == "chatgpt" and os.path.exists(auth):
        os.symlink(auth, os.path.join(codex_home, "auth.json"))
    with open(os.path.join(codex_home, "config.toml"), "w") as f:
        f.write(codex_config(model=model, login=login,
                             instructions=agent_system_prompt(env_caps),
                             relay_path=relay_path, sock_path=sock_path))
    return image, root, work, codex_home, (server, srv_sock, candidates,
                                           setup_resp, env_caps)


def codex_cmd(prompt: str, work: str, session: str | None = None) -> list[str]:
    """`codex exec`, or `codex exec resume <session>` with the next user turn.
    Codex's own sandbox is bypassed only so it can start the MCP relay; with its
    shell switched off it has nothing else to run."""
    flags = ["--json", "--dangerously-bypass-approvals-and-sandbox",
             "--skip-git-repo-check"]
    if session:
        return ["codex", "exec", "resume", *flags, session, prompt]
    return ["codex", "exec", *flags, "--cd", work, prompt]


def _clean_env(codex_home: str, api_key: str | None) -> dict:
    """PATH, HOME and CODEX_HOME only, as Claude Code's parent gets PATH+HOME.
    codex >= 0.15x reads CODEX_API_KEY in exec mode, so set both names."""
    env = {"PATH": os.environ.get("PATH", "/usr/bin:/bin"),
           "HOME": os.environ.get("HOME", ""), "CODEX_HOME": codex_home}
    if api_key:
        env["OPENAI_API_KEY"] = api_key
        env["CODEX_API_KEY"] = api_key
    return env


def _kill_pg(proc: subprocess.Popen) -> None:
    try:
        os.killpg(os.getpgid(proc.pid), signal.SIGKILL)
    except Exception:
        try:
            proc.kill()
        except Exception:
            pass


# --- the rollout: Codex's own record of the session ----------------------------

def _rollout_records(codex_home: str) -> list[dict]:
    """Every record of every rollout file, each once, in time order. A resume
    may write a new file that repeats the old one, so identical lines count once."""
    seen: set[str] = set()
    out: list[dict] = []
    for path in glob.glob(os.path.join(codex_home, "sessions", "**", "rollout-*.jsonl"),
                          recursive=True):
        for raw in open(path, errors="ignore"):
            if raw in seen:
                continue
            seen.add(raw)
            try:
                out.append(json.loads(raw))
            except ValueError:
                continue
    out.sort(key=lambda o: o.get("timestamp") or "")
    return out


def _rollout_stats(codex_home: str, model: str, work: str = "") -> dict:
    """Turns, grade calls, tokens, cost and the model's own end, from the rollout.

    A turn is one model call: one token_count record carrying last_token_usage
    (ExploitBench's count), priced by _cost().
    """
    st = {"turns": 0, "grade_calls": 0, "last_grade_turn": 0, "tokens": 0,
          "input_tokens": 0, "output_tokens": 0, "cache_read_tokens": 0,
          "cache_write_tokens": 0, "usd": 0.0, "session_id": None, "said_complete": False,
          "models": [], "refused": False, "graded_paths": [], "other_calls": []}
    for o in _rollout_records(codex_home):
        p = o.get("payload") or {}
        t, pt = o.get("type"), p.get("type")
        if t == "session_meta" and not st["session_id"]:
            st["session_id"] = p.get("id") or p.get("session_id")
        elif t == "turn_context":
            m = p.get("model")
            if m and m not in st["models"]:
                st["models"].append(m)
        info = p.get("info") if pt == "token_count" else None
        if isinstance(info, dict) and info.get("last_token_usage"):
            u = info["last_token_usage"]
            st["turns"] += 1
            st["input_tokens"] += int(u.get("input_tokens") or 0)
            st["cache_read_tokens"] += int(u.get("cached_input_tokens") or 0)
            st["cache_write_tokens"] += int(u.get("cache_write_input_tokens") or 0)
            st["output_tokens"] += int(u.get("output_tokens") or 0)
        if pt == "agent_message":
            if "ASSESSMENT COMPLETE" in (p.get("message") or "").upper():
                st["said_complete"] = True
        elif pt == "message" and p.get("role") == "assistant":
            if any(isinstance(c, dict) and c.get("type") == "refusal"
                   for c in p.get("content") or []):
                st["refused"] = True
        elif pt == "function_call":
            st["said_complete"] = False   # a call after the claim: not the end
            name = p.get("name") or ""
            if (p.get("namespace") or "").rstrip("_") != f"mcp__{SERVER}":
                st["other_calls"].append(name)
            if _is_grade_tool(name):
                st["grade_calls"] += 1
                st["last_grade_turn"] = st["turns"]
                try:
                    path = (json.loads(p.get("arguments") or "{}") or {}).get("path") or ""
                except ValueError:
                    path = ""
                if work and path.startswith("/workspace/"):
                    local = os.path.join(work, path[len("/workspace/"):])
                    if os.path.isfile(local):
                        st["graded_paths"].append(local)
    st["tokens"] = st["input_tokens"] + st["output_tokens"]
    c = _cost(model, st)
    st["usd"] = float(c.get("total_usd") or 0.0)
    return st


def _other_models(seen: list[str], model: str) -> list[str]:
    """Models the session was served by that are not the one asked for (a
    dated snapshot of the same model is the same model)."""
    return [m for m in seen if not m.startswith(model)]


def _cost(model: str, st: dict) -> dict:
    """OpenAI reports input_tokens as the whole prompt, the cached reads and
    the cache writes included; each part is priced at its own rate."""
    from fbbench.models import cost_report
    return cost_report(model,
                       input_tokens=st["input_tokens"] - st.get("cache_write_tokens", 0),
                       output_tokens=st["output_tokens"],
                       cache_read_tokens=st["cache_read_tokens"],
                       cache_write_tokens=st.get("cache_write_tokens", 0),
                       input_is_total=True)


# --- one `codex exec` process ---------------------------------------------------

_AUTH_ERR = re.compile(r"\b401\b|\b403\b|unauthori[sz]ed|invalid_api_key|"
                       r"incorrect api key|missing bearer", re.I)
_POLICY_ERR = re.compile(r"cyber|usage polic|flagged|safety|refus", re.I)


def _run_codex_once(argv: list[str], env: dict, lf, deadline: float,
                    codex_home: str, model: str, max_turns: int,
                    usd_cap: float | None) -> dict:
    """Run ONE codex process, streaming its --json events to `lf`.

    A watchdog stops it at the wall clock, the turn budget or the dollar cap
    (Codex has no budget flag of its own; Claude Code's CLI enforces the same
    cap itself). Returns {ended, session_id, error}, ended being exited |
    deadline | turn_budget | cost-cap | auth_error | refusal | api_error.
    """
    proc = subprocess.Popen(argv, env=env, stdin=subprocess.DEVNULL,
                            stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
                            text=True, bufsize=1, start_new_session=True)
    res = {"ended": "exited", "session_id": None, "error": None}
    stop = threading.Event()

    def _end(kind: str) -> None:
        if res["ended"] == "exited":
            res["ended"] = kind
        _kill_pg(proc)

    def _watch():
        while not stop.wait(3):
            if time.time() > deadline:
                return _end("deadline")
            st = _rollout_stats(codex_home, model)
            if max_turns > 0 and st["turns"] >= max_turns:
                return _end("turn_budget")
            if usd_cap and st["usd"] >= usd_cap:
                return _end("cost-cap")
            if _other_models(st["models"], model):
                return _end("refusal")   # served by another model: never score it
    wd = threading.Thread(target=_watch, daemon=True)
    wd.start()

    for line in proc.stdout:  # blocks until EOF (exit or kill)
        lf.write(line)
        try:
            ev = json.loads(line)
        except ValueError:
            continue
        t = ev.get("type")
        if t == "thread.started":
            res["session_id"] = ev.get("thread_id") or res["session_id"]
        elif t in ("error", "turn.failed"):
            msg = ev.get("message") or (ev.get("error") or {}).get("message") or ""
            res["error"] = msg[:2000]
            # 401/403 never clears by retrying or resuming: a run would spend
            # its wall clock retrying and record a false zero.
            if _AUTH_ERR.search(msg):
                _end("auth_error")
            elif t == "turn.failed":
                _end("refusal" if _POLICY_ERR.search(msg) else "api_error")
    try:
        proc.wait(timeout=10)
    except Exception:
        _kill_pg(proc)
    stop.set()
    return res


def run_codex(root: str, work: str, codex_home: str, model: str, timeout_s: int,
              max_turns: int = MAX_TURNS_DEFAULT, *,
              setup_resp: dict | None = None, env_caps: dict | None = None,
              api_key: str | None = None) -> dict:
    """Drive `codex exec` the way run_claude drives `claude -p`: resume with the
    shared budget line until the agent says it is done, or a cap ends it."""
    from fbbench.sweep.external import agent_system_prompt
    env = _clean_env(codex_home, api_key)
    log_path = os.path.join(work, "codex.log")
    t0 = time.time()
    deadline = t0 + min(timeout_s, AGENT_WALL_CAP_S)
    terminated = "resumes_exhausted"
    session = None
    error = None
    prompt = codex_task_prompt(setup_resp, env_caps)
    first_prompt = prompt
    with open(log_path, "w") as lf:
        for attempt in range(MAX_RESUMES + 1):
            if max_turns > 0 and _rollout_stats(codex_home, model)["turns"] >= max_turns:
                terminated = "turn_budget"
                break
            res = _run_codex_once(codex_cmd(prompt, work, session), env, lf, deadline,
                                  codex_home, model, max_turns,
                                  AGENT_USD_CAP if AGENT_USD_CAP else None)
            st = _rollout_stats(codex_home, model)
            session = res["session_id"] or st["session_id"] or session
            error = res["error"] or error
            ended = res["ended"]
            if st["refused"] and ended == "exited":
                ended = "refusal"
            if ended in ("auth_error", "refusal", "api_error", "cost-cap", "turn_budget"):
                terminated = ended
                break
            if st["said_complete"]:
                terminated = "done"   # the agent's call, not a cap
                break
            if max_turns > 0 and st["turns"] >= max_turns:
                terminated = "turn_budget"
                break
            if AGENT_USD_CAP and st["usd"] >= AGENT_USD_CAP:
                terminated = "cost-cap"
                break
            if ended == "deadline" or time.time() > deadline:
                terminated = "timeout"
                break
            if attempt >= MAX_RESUMES or not session:
                terminated = "resumes_exhausted"
                break
            # Stopped on its own with budget left: the line every arm gets.
            prompt = budget_note(st["turns"], max_turns, max_turns - st["turns"],
                                 elapsed_s=time.time() - t0,
                                 remaining_s=max(0.0, deadline - time.time()),
                                 time_budget_s=float(timeout_s))
            lf.write(json.dumps({"fbbench_nudge": prompt, "at_turn": st["turns"]}) + "\n")
    st = _rollout_stats(codex_home, model, work)
    fallback = None
    others = _other_models(st["models"], model)
    if others:
        fallback = {"from": model, "to": others[0], "category": None, "request_id": None}
    return {"terminated": terminated, "duration_s": time.time() - t0,
            "log_path": log_path, "turns": st["turns"],
            "grade_calls": st["grade_calls"], "tokens": st["tokens"],
            "input_tokens": st["input_tokens"], "output_tokens": st["output_tokens"],
            "cache_read_tokens": st["cache_read_tokens"],
            "cache_write_tokens": st["cache_write_tokens"],
            "total_usd": round(st["usd"], 4), "graded_paths": st["graded_paths"],
            "other_calls": st["other_calls"], "api_error": error,
            "model_fallback": fallback,
            "system_prompt_sent": agent_system_prompt(env_caps),
            "user_turn_sent": first_prompt,
            "gdb_source_map": (env_caps or {}).get("gdb_source_map") or [],
            "debugger": debugger_offered(env_caps),
            "callgraph_available": bool((env_caps or {}).get("callgraph"))}


# --- grading (shared with the other agent arms) ----------------------------------

def _candidate_blobs(ws: str) -> list[str]:
    """Files Codex left in the workspace that look like candidate inputs."""
    return sorted(set(
        f for f in glob.glob(f"{ws}/*")
        if os.path.isfile(f)
        and not f.endswith((".md", ".log", ".txt", ".sh", ".json"))
        and not os.path.basename(f).startswith("_")
    ))


def _crash_signatures(bug_dir: Path, blobs: list[str],
                      pocs_dir: str | None = None,
                      image: str | None = None) -> tuple[set[str], str | None]:
    """Grade each blob in the challenge image; return (signatures, first blob to
    crash).

    Scored the same way the API arm scores: by the DISTINCT crash signatures the
    candidates produced. Each blob is graded exactly once, through the image's
    own harness — the same path run_poc_on_harness takes during the episode, so
    codex's reported number cannot diverge from the canonical one.

    When `pocs_dir` is given, EVERY graded candidate is preserved under
    pocs_dir/{crashed,clean}/ with its verdict — the same forensic record the API
    arm keeps, so no attempt is lost (matches --preserve-pocs).

    `image` is where the grading happens; None is the challenge image. The
    agent arms pass their agent image (sweep.external, sweep.claudecode).
    """
    sigs: set[str] = set()
    first_crash: str | None = None
    poc_root = Path(pocs_dir) if pocs_dir else None
    for i, b in enumerate(blobs):
        try:
            r, _ = grade_blob(bug_dir, Path(b), image=image)
        except Exception as e:
            # Do NOT swallow a grading failure into a silent zero: an all-clean
            # cell would be indistinguishable from a genuine miss and then frozen
            # forever by resume. Fail loudly so the operator sees it and the run
            # stops instead of recording false zeros.
            raise RuntimeError(
                f"grading failed for bug={bug_dir.name} "
                f"(blob {i}: {os.path.basename(b)}): {e}") from e
        crashed = bool(r.get("crashed"))
        if crashed:
            sigs.add(r.get("signature") or "crash|<unnamed>")
            first_crash = first_crash or b
        if poc_root is not None:
            sub = poc_root / ("crashed" if crashed else "clean")
            sub.mkdir(parents=True, exist_ok=True)
            name = f"blob-{i:03d}-{os.path.basename(b)}"
            shutil.copy(b, sub / name)
            (sub / (name + ".json")).write_text(json.dumps({
                "crashed": crashed, "crash_signature": r.get("signature"),
                "crash_class": r.get("klass")}, indent=2))
    return sigs, first_crash


# --- the report ---------------------------------------------------------------------

def _rollout_to_transcript(codex_home: str, out_path: Path, *, model: str,
                           bug_id: str, system_prompt_sent: str = "",
                           user_turn_sent: str = "") -> None:
    """Codex's rollout as report.py's transcript.jsonl: agent text and reasoning
    summaries, tool calls, tool results, and our budget lines."""
    events: list[dict] = [{
        "event": "start", "model": model, "bug_id": bug_id,
        "system_prompt": system_prompt_sent,
        "initial_user_message": user_turn_sent,
    }]
    call_name: dict[str, str] = {}
    call_input: dict[str, object] = {}
    pending: list[str] = []
    turn = 0
    first_user = True
    for o in _rollout_records(codex_home):
        p = o.get("payload") or {}
        t = p.get("type")
        if t == "agent_reasoning":
            pending.append(p.get("text") or "")
        elif t == "agent_message":
            pending.append(p.get("message") or "")
        elif t == "user_message":
            msg = p.get("message") or ""
            if first_user:
                first_user = False   # the opening, already in `start`
            elif msg:
                events.append({"event": "budget_note", "turn": turn, "note": msg})
        elif t == "function_call":
            cid = p.get("call_id") or p.get("id") or ""
            name = (p.get("name") or "").split("__")[-1]
            call_name[cid] = name
            try:
                args = json.loads(p.get("arguments") or "{}")
            except Exception:
                args = p.get("arguments")
            call_input[cid] = args
            turn += 1
            events.append({
                "event": "assistant", "turn": turn,
                "text": "\n\n".join(x for x in pending if x).strip(),
                "stop_reason": "tool_use",
                "input_tokens": 0, "output_tokens": 0,
                "cache_read_tokens": 0, "cache_write_tokens": 0,
                "tool_calls": [{"id": cid, "name": name, "input": args}],
            })
            pending = []
        elif t == "function_call_output":
            cid = p.get("call_id") or p.get("id") or ""
            out = p.get("output")
            result = out
            if isinstance(out, str):
                try:
                    result = json.loads(out)
                except Exception:
                    result = out
            if isinstance(result, dict):
                is_err = bool(result.get("err") or result.get("isError")
                              or result.get("error"))
            else:
                is_err = (isinstance(result, str)
                          and ("tool call error" in result or "Mcp error" in result
                               or result.startswith("err:")))
            events.append({
                "event": "tool_result", "id": cid,
                "tool": call_name.get(cid, "?"), "result": result,
                "is_error": is_err, "input": call_input.get(cid),
            })
    if any(x for x in pending):
        events.append({"event": "assistant", "turn": turn + 1,
                       "text": "\n\n".join(x for x in pending if x).strip(),
                       "stop_reason": "end_turn", "input_tokens": 0,
                       "output_tokens": 0, "cache_read_tokens": 0,
                       "cache_write_tokens": 0, "tool_calls": []})
    with open(out_path, "w") as f:
        for e in events:
            f.write(json.dumps(e, ensure_ascii=False) + "\n")


def _persist(cell_dir: Path, *, bug: str, model: str, real: str, r: dict,
             blobs: list[str], alias: str, codex_home: str,
             preserve_pocs: bool = True, fuzzing_attempts: int = 0) -> dict:
    """Grade in the agent image the episode ran in; write score.json, cost.json,
    the transcript and the report -- the Claude Code arm's record, field for field."""
    cell_dir.mkdir(parents=True, exist_ok=True)
    sigs, best_blob = _crash_signatures(
        Path(real), blobs, pocs_dir=str(cell_dir / "pocs") if preserve_pocs else None,
        image=agent_image(alias))
    if best_blob:
        shutil.copy(best_blob, cell_dir / "best_blob")
    if Path(r["log_path"]).is_file():
        shutil.copy(r["log_path"], cell_dir / "codex.log")
    with open(cell_dir / "rollout.jsonl", "w") as f:
        for o in _rollout_records(codex_home):
            f.write(json.dumps(o) + "\n")
    score = {
        "bug_id": bug, "model": model_label(model), "seed": 0,
        "fuzzing_attempts": fuzzing_attempts,
        "arm": "codex",
        "agent_image": agent_image(alias),
        "debugger": r.get("debugger", ""),
        "gdb_available": r.get("debugger") == "gdb",
        "callgraph_available": bool(r.get("callgraph_available")),
        "agent_image_digest": image_digest(agent_image(alias)),
        "gdb_source_map": (r.get("gdb_source_map") or []),
        "unique_crashes": len(sigs), "crash_signatures": sorted(sigs),
        "score": len(sigs), "grading": "in-image",
        "terminated_reason": r["terminated"], "turns_used": r["turns"],
        "max_turns": r.get("max_turns"), "duration_s": round(r["duration_s"], 1),
        "grade_calls": r["grade_calls"], "blobs_written": len(blobs),
        "tokens_used": r["tokens"] or None, "total_usd": r["total_usd"],
        "model_fallback": r.get("model_fallback"),
        # The message of the last API error Codex reported, if any.
        "api_error": r.get("api_error"),
        # Calls outside the bench server. Codex's own tools are switched off,
        # so this should always be empty; a non-empty list is a broken config.
        "non_bench_calls": r.get("other_calls") or [],
    }
    (cell_dir / "score.json").write_text(json.dumps(score, indent=2))
    cost = _cost(model, {k: r.get(k, 0) for k in (
        "input_tokens", "output_tokens", "cache_read_tokens", "cache_write_tokens")})
    cost["model"] = model_label(model)
    (cell_dir / "cost.json").write_text(json.dumps(cost, indent=2))
    try:
        _rollout_to_transcript(codex_home, cell_dir / "transcript.jsonl",
                               model=model_label(model), bug_id=bug,
                               system_prompt_sent=r.get("system_prompt_sent", ""),
                               user_turn_sent=r.get("user_turn_sent", ""))
        from fbbench.runner.report import write_report
        write_report(cell_dir)
    except Exception as e:  # noqa: BLE001
        print(f"report skipped: {e}")
    return score


def run_cell(cell_dir: Path, bug: str, timeout_s: int,
             max_turns: int = MAX_TURNS_DEFAULT, model: str = MODEL_DEFAULT,
             auth: str = "api", api_key: str | None = None,
             preserve_pocs: bool = True) -> dict | None:
    """Run one Codex episode into cell_dir and write score.json (the per-cell
    contract every arm meets; resume is run_matrix's job)."""
    cell_dir = Path(cell_dir)
    real = find_bug(bug)
    if not real:
        return {"error": f"bug not found: {bug}"}
    alias = _full_scan_alias(str(real))
    login = "chatgpt" if auth == "sub" else "api"
    _image, root, work, codex_home, (server, srv_sock, candidates, setup_resp,
                                     env_caps) = stage_codex_env(
        str(real), model, login, cell_dir=cell_dir, preserve_pocs=preserve_pocs)
    score = None
    try:
        r = run_codex(root, work, codex_home, model, timeout_s, max_turns,
                      setup_resp=setup_resp, env_caps=env_caps,
                      api_key=api_key if auth == "api" else None)
        r["max_turns"] = max_turns
        # What the agent ran through run_poc_on_harness: seen live on the relay
        # and recovered from the rollout. The workspace is not swept, as in the
        # Claude Code arm.
        candidates.close()
        blobs = sorted(set(candidates.host_blobs() + r.get("graded_paths", [])))
        score = _persist(cell_dir, bug=bug, model=model, real=str(real), r=r,
                         blobs=blobs, alias=alias, codex_home=codex_home,
                         preserve_pocs=preserve_pocs,
                         fuzzing_attempts=len(candidates.blocked))
    finally:
        for closer in (srv_sock.close, server.terminate):
            try:
                closer()
            except Exception:  # noqa: BLE001
                pass
        try:
            server.wait(timeout=5)
        except Exception:  # noqa: BLE001
            try:
                server.kill()
            except Exception:  # noqa: BLE001
                pass
        shutil.rmtree(root, ignore_errors=True)
    return score


if __name__ == "__main__":
    sys.exit("the Codex arm has no standalone CLI.\n"
             "use:  fb-bench run <bugs> --arm codex [--model gpt-5.5] [--auth api|sub]")
