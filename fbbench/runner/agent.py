"""Native AGENT arm for FuzzingBrain Bench — the built-in "agent model".

Same MCP tool surface, backends, grading, and score/transcript outputs as the
primary tool-loop (runner/episode.py), but driven like a real coding agent
(Codex / Claude Code): the model keeps a persistent plan (a synthetic
`update_plan` tool), is paced to TEST OFTEN (forced first run_input + a cadence
nudge), gets a short REFLECTION after every run_input, and is steered by the
agent system prompt toward building the harness locally and fuzzing it.

The goal is to lift a given base model (e.g. claude-haiku-4-5) to the level of
the vendor-agent leaderboard entries, using only the bench's own tools.

run_agent_episode() mirrors run_episode()'s signature and returns the same
EpisodeResult, so runner/__main__.py can dispatch to it and the whole
score.json / cost.json / report pipeline is unchanged.
"""
from __future__ import annotations

import json
import os
import shutil
import time
from pathlib import Path

from fbbench.prompts import (
    AGENT_FIRST_TEST_NUDGE, AGENT_PLAN_TOOL, AGENT_REFLECT_CLEAN_NUDGE,
    AGENT_REFLECT_FAULT_NUDGE, AGENT_SYSTEM_PROMPT, AGENT_TEST_CADENCE_NUDGE,
    FORCE_FULL_NUDGE, REQUIRE_PRESET_NUDGE, TRUNCATION_NUDGE, budget_note,
    build_initial_user_message,
)
from fbbench.runner.backends.base import Completion, ToolResult
from fbbench.runner.episode import (
    EpisodeResult, _GRADE_TOOLS, _is_malformed, _is_refusal, _is_truncated,
    neutral_tools,
)
from fbbench.runner.mcp_client import MCPClient, MCPToolError

# The synthetic plan tool is handled in-loop and NEVER forwarded to the MCP
# server (the server would reject an unknown tool). Keep the name in one place.
_PLAN_TOOL = "update_plan"

# Signals in a harness_output that mean the candidate FAULTED (so the reflection
# nudge congratulates instead of coaching). Kept broad on purpose — it only
# picks which nudge text to append; the authoritative verdict is the oracle's.
_FAULT_MARKERS = (
    "addresssanitizer", "leaksanitizer", "undefinedbehaviorsanitizer",
    "runtime error:", "libfuzzer: deadly signal", "libfuzzer: out-of-memory",
    "==abort", "sanitizer", "segv on unknown address", "sigabrt",
    "stack-buffer-overflow", "heap-buffer-overflow", "use-after-free",
    "uncaught exception", "java.lang.", "== error", "deadlysignal",
)


def _looks_like_fault(out: dict) -> bool:
    """Heuristic: does this run_input harness_output look like a crash? Used only
    to pick the reflection nudge — the real score comes from the oracle verdict."""
    ho = out.get("harness_output", {}) if isinstance(out, dict) else {}
    if not isinstance(ho, dict):
        blob = str(ho).lower()
    else:
        # A fatal signal or non-zero abort exit is already a strong tell.
        if ho.get("signal") not in (None, 0, "0"):
            return True
        blob = (str(ho.get("stderr", "")) + "\n" + str(ho.get("stdout", ""))).lower()
    return any(m in blob for m in _FAULT_MARKERS)


def _plan_hint(plan: str) -> str:
    """A one-line ' [Your current plan: ...]' reminder for the cadence/clean
    nudges, or '' when the model hasn't set a plan yet."""
    plan = (plan or "").strip().replace("\n", " ")
    if not plan:
        return ""
    if len(plan) > 240:
        plan = plan[:237] + "..."
    return f" [Your current plan: {plan}]"


def run_agent_episode(
    backend,
    bug_id: str,
    bug_dir: str,
    workspace: str,
    server_bin: str,
    max_turns: int = 100,
    episode_log: str | None = None,
    oracle_dir: str | None = None,
    capability_set: list[str] | None = None,
    pocs_dir: str | None = None,
    force_full: bool = False,
    full_scan: bool = False,
    require_preset: bool = False,
    image: str | None = None,
) -> EpisodeResult:
    mcp = MCPClient(server_bin, bug_dir=bug_dir, workspace=workspace,
                    oracle_dir=oracle_dir, image=image)
    mcp.initialize()
    kb: set[str] = set(capability_set or ["reach", "crash", "class", "site"])
    poc_root: Path | None = Path(pocs_dir) if pocs_dir else None
    grade_idx = 0

    setup_resp = mcp.call("setup", {})
    bug_desc = setup_resp.get("task", setup_resp.get("bug_desc", ""))
    user_text = build_initial_user_message(bug_desc, setup_resp, full_scan=full_scan)
    sysp = AGENT_SYSTEM_PROMPT

    messages: list[dict] = [{"role": "user", "content": user_text}]
    # The plan tool is advertised alongside the real MCP tools; it is intercepted
    # in-loop and never reaches the server.
    tools = neutral_tools(mcp) + [AGENT_PLAN_TOOL]
    result = EpisodeResult(bug_id=bug_id, model=backend.model)
    log_fp = open(episode_log, "w") if episode_log else None
    tlog_fp = (open(os.path.join(os.path.dirname(episode_log), "transcript.jsonl"), "w")
               if episode_log else None)
    start = time.time()

    def log(record: dict) -> None:
        if log_fp:
            log_fp.write(json.dumps(record) + "\n")
            log_fp.flush()

    def tlog(record: dict) -> None:
        if tlog_fp:
            tlog_fp.write(json.dumps(record, ensure_ascii=False) + "\n")
            tlog_fp.flush()

    def _payload_obj(payload: str):
        try:
            return json.loads(payload)
        except (ValueError, TypeError):
            return payload

    log({"event": "start", "model": backend.model, "bug_id": bug_id,
         "arm": "agent", "capability_set": sorted(kb),
         "preserve_pocs": bool(poc_root), "system_prompt_chars": len(sysp)})
    tlog({"event": "start", "model": backend.model, "bug_id": bug_id,
          "arm": "agent", "capability_set": sorted(kb), "max_turns": max_turns,
          "preserve_pocs": bool(poc_root), "system_prompt": sysp,
          "initial_user_message": user_text, "tools": tools})

    def complete_once() -> Completion:
        c = backend.complete(sysp, messages, tools, max_tokens=65536)
        result.input_tokens += c.input_tokens
        result.output_tokens += c.output_tokens
        result.cache_read_tokens += c.cache_read_tokens
        result.cache_write_tokens += c.cache_write_tokens
        return c

    # --- agent state: plan + test-often pacing -----------------------------
    plan_text = ""
    last_test_turn = -1          # turn index of the most recent run_input call
    any_test = False             # has run_input ever been called?
    # Force a first test early, then keep a steady cadence. Scaled to the budget
    # so 50-turn diff-scan and 100-turn full-scan both stay in the loop.
    first_by = max(6, max_turns // 12)
    cadence = max(5, max_turns // 12)

    consecutive_trunc = 0
    try:
        for turn in range(max_turns):
            result.turns_used = turn + 1
            comp = complete_once()
            for attempt in range(3):
                if comp.tool_calls or not (_is_refusal(comp) or _is_malformed(comp)):
                    break
                kind = "refusal" if _is_refusal(comp) else "malformed_function_call"
                if kind == "refusal":
                    result.refusal_retries += 1
                else:
                    result.malformed_retries += 1
                log({"event": "retry", "kind": kind, "turn": turn,
                     "attempt": attempt + 1, "stop_reason": comp.stop_reason})
                tlog({"event": "retry", "kind": kind, "turn": turn,
                      "attempt": attempt + 1, "stop_reason": comp.stop_reason,
                      "text": comp.text})
                comp = complete_once()

            messages.append({"role": "assistant", "text": comp.text,
                             "tool_calls": comp.tool_calls})
            log({"event": "assistant", "turn": turn, "text": comp.text,
                 "stop_reason": comp.stop_reason, "tool_calls": len(comp.tool_calls)})
            tlog({"event": "assistant", "turn": turn, "text": comp.text,
                  "stop_reason": comp.stop_reason,
                  "input_tokens": comp.input_tokens, "output_tokens": comp.output_tokens,
                  "cache_read_tokens": comp.cache_read_tokens,
                  "cache_write_tokens": comp.cache_write_tokens,
                  "tool_calls": [{"id": tc.id, "name": tc.name, "input": tc.input}
                                 for tc in comp.tool_calls]})

            if not comp.tool_calls:
                if _is_truncated(comp):
                    consecutive_trunc += 1
                    if consecutive_trunc >= 1:
                        result.terminated_reason = "truncation_stuck"
                        break
                    messages.append({"role": "user", "content": TRUNCATION_NUDGE})
                    continue
                would_stop = ("refusal" if _is_refusal(comp)
                              else "malformed_function_call" if _is_malformed(comp)
                              else "voluntary" if ("ASSESSMENT COMPLETE" in comp.text.upper()
                                                   or "EPISODE COMPLETE" in comp.text.upper())
                              else "no_tool_use")
                if require_preset:
                    fired = {k for k, v in result.capabilities.items() if v == "fired"}
                    if not (kb and kb.issubset(fired)):
                        messages.append({"role": "user", "content": REQUIRE_PRESET_NUDGE})
                        log({"event": "require_preset_continue", "turn": turn,
                             "would_stop": would_stop, "fired": sorted(fired)})
                        continue
                if force_full:
                    messages.append({"role": "user", "content": FORCE_FULL_NUDGE})
                    log({"event": "force_continue", "turn": turn, "would_stop": would_stop})
                    continue
                result.terminated_reason = would_stop
                break
            consecutive_trunc = 0

            results: list[ToolResult] = []
            tested_this_turn = False
            faulted_this_turn = False
            for tc in comp.tool_calls:
                # --- synthetic plan tool: handled here, never sent to MCP -----
                if tc.name == _PLAN_TOOL:
                    plan_text = str((tc.input or {}).get("plan", "")).strip()
                    payload = json.dumps({"ok": True, "plan_recorded": True})
                    results.append(ToolResult(id=tc.id, name=tc.name,
                                              content=payload, is_error=False))
                    log({"event": "plan_update", "turn": turn,
                         "plan_chars": len(plan_text)})
                    tlog({"event": "tool_result", "turn": turn, "tool": tc.name,
                          "id": tc.id, "input": tc.input or {}, "is_error": False,
                          "result": {"ok": True, "plan_recorded": True}})
                    continue

                try:
                    out = mcp.call(tc.name, tc.input or {})
                    is_error = False
                except MCPToolError as e:
                    out = {"error": str(e), "data": e.data}
                    is_error = True

                if tc.name in _GRADE_TOOLS and not is_error:
                    tested_this_turn = True
                    result.last_grade = out
                    caps_now = out.get("capabilities", {})
                    for cap, status in caps_now.items():
                        if result.capabilities.get(cap) == "fired":
                            continue
                        result.capabilities[cap] = status

                    if poc_root is not None:
                        grade_idx += 1
                        src = (tc.input or {}).get("path", "")
                        if src and os.path.isfile(src):
                            fired_now = {k for k, v in caps_now.items() if v == "fired"}
                            solved = kb.issubset(fired_now) and bool(kb)
                            sub = poc_root / ("solved" if solved else "failed")
                            sub.mkdir(parents=True, exist_ok=True)
                            stem = f"blob-{grade_idx:03d}-turn{turn:02d}"
                            shutil.copy2(src, sub / f"{stem}.bin")
                            (sub / f"{stem}.json").write_text(json.dumps({
                                "turn": turn,
                                "tier_score": sum(1 for v in caps_now.values() if v == "fired"),
                                "fired": sorted(fired_now),
                                "k_b": sorted(kb),
                                "solved": solved,
                                "agreed": out.get("agreed"),
                            }, indent=2))

                    harness_out = {"harness_output": out.get("harness_output", {})}
                    faulted_this_turn = faulted_this_turn or _looks_like_fault(out)
                    payload = json.dumps(harness_out)
                else:
                    payload = json.dumps(out)

                results.append(ToolResult(id=tc.id, name=tc.name,
                                          content=payload, is_error=is_error))
                log({"event": "tool_result", "turn": turn, "tool": tc.name,
                     "is_error": is_error, "result_chars": len(payload)})
                tlog({"event": "tool_result", "turn": turn, "tool": tc.name,
                      "id": tc.id, "input": tc.input or {}, "is_error": is_error,
                      "result": _payload_obj(payload)})

            if tested_this_turn:
                any_test = True
                last_test_turn = turn

            # --- pacing + reflection: appended to the tool-result user turn ---
            done_t = turn + 1
            remaining = max_turns - done_t
            note = budget_note(done_t, max_turns, remaining)
            coach = ""
            if tested_this_turn:
                coach = (AGENT_REFLECT_FAULT_NUDGE if faulted_this_turn
                         else AGENT_REFLECT_CLEAN_NUDGE.format(plan=_plan_hint(plan_text)))
            elif not any_test and done_t >= first_by:
                coach = AGENT_FIRST_TEST_NUDGE
            elif any_test and (turn - last_test_turn) >= cadence:
                coach = AGENT_TEST_CADENCE_NUDGE.format(plan=_plan_hint(plan_text))
            if coach:
                note = f"{note}\n\n{coach}"
                tlog({"event": "agent_coach", "turn": turn, "note": coach})

            messages.append({"role": "tool", "results": results, "note": note})
            tlog({"event": "budget_note", "turn": turn, "note": note})
        else:
            result.terminated_reason = "max_turns"
    except Exception as e:
        result.terminated_reason = "error"
        result.error = f"{type(e).__name__}: {e}"
        log({"event": "error", "turn": result.turns_used, "error": result.error})
        tlog({"event": "error", "turn": result.turns_used, "error": result.error})
    finally:
        result.duration_s = time.time() - start
        log({"event": "end", "terminated_reason": result.terminated_reason,
             "capabilities": result.capabilities, "turns_used": result.turns_used,
             "duration_s": result.duration_s,
             "input_tokens": result.input_tokens, "output_tokens": result.output_tokens})
        tlog({"event": "end", "terminated_reason": result.terminated_reason,
              "capabilities": result.capabilities, "turns_used": result.turns_used,
              "duration_s": result.duration_s,
              "input_tokens": result.input_tokens, "output_tokens": result.output_tokens})
        if log_fp:
            log_fp.close()
        if tlog_fp:
            tlog_fp.close()
            try:
                from fbbench.runner.traj import write_traj
                d = os.path.dirname(episode_log)
                write_traj(os.path.join(d, "transcript.jsonl"), d,
                           f"{bug_id} / {backend.model} (agent)")
            except Exception:
                pass
        mcp.close()
    return result
