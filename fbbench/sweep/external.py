"""The generic external-agent arm: run ANY agent the bench does not contain.

    fb-bench run <bugs> --agent path/to/agent.yaml

There is no per-agent code here. An agent is described by a small manifest and
lives in its own repository; this arm gives it the one contract every agent
plugs into and grades what it produced -- the same in-image grader every other
arm uses, so a crash counted here means what it means everywhere.

The contract, the whole waist between bench and agent:

    1. a directory of the challenge source     (this arm stages it from the
                                                 sealed image; the answer is not
                                                 in it, and that is asserted)
    2. a `submit <file>` command in that dir    (this arm provides it; it runs
                                                 the candidate against the sealed
                                                 harness and returns the verdict)

The agent is a command run in that directory. It never touches Docker, never
learns the image name, never learns which version it is looking at -- the source
it reads and the harness its candidate runs on both come from the one sealed
image, so they cannot disagree.

Manifest (YAML or JSON):

    name: fbagent
    command: >
      omp -p "{opening}" --tools read,glob,grep,bash
      --system-prompt @fuzzing-brain.md --no-lsp --no-skills --no-session
      --auto-approve --max-time {timeout}
    network: blocked            # or: allowed
    shell_env: OMP_SHELL_PATH   # the env var the agent reads its shell from;
                                # the bench points it at the sandbox wrapper so
                                # the agent's shell inherits the masked Docker
                                # socket and (blocked) the empty net namespace

Template fields in `command`: {workspace} {timeout} {opening} {submit}.
`@path` inside the command is read relative to the manifest and inlined, so a
long system prompt lives in its own file next to the manifest.
"""

from __future__ import annotations

import json
import os
import shlex
import re
import shutil
import signal
import subprocess
import tempfile
import threading
import time
from pathlib import Path
from typing import Callable

from fbbench.models import cost_usd
from fbbench.grading import find_bug, grade_blob
from fbbench.images import agent_image, image_digest
from fbbench.prompts import build_initial_user_message, system_prompt
from fbbench.sweep.codex import _crash_signatures
from fbbench.sweep.mcp_episode import (
    fetch_setup, probe_environment,
    AGENT_USD_CAP, AGENT_WALL_CAP_S, CandidateLog, _start_episode_server,
    agent_tools_note, with_agent_tools)
from fbbench.runner.mcp_client import _full_scan_alias

# The first user turn an external agent gets: the api arm's opening, verbatim.
# An external agent drives the same three tools under the same bare names, so
# it needs no substitution -- and an arm graded on different wording would be
# measuring the wording.
def default_opening(setup_resp: dict | None = None) -> str:
    """The api arm's first user turn, verbatim.

    Not system_prompt(): that is the api arm's SYSTEM prompt and belongs in the
    system slot. This is build_initial_user_message(), which carries the one
    thing nothing else does -- the per-bug sanitizer and build-env block. With
    no setup response the context block is empty rather than absent, so an arm
    whose server did not answer still gets the same instructions.
    """
    return build_initial_user_message(setup_resp or {})


DEFAULT_OPENING = default_opening()
"""The api arm's first user turn with no per-bug context filled in."""


def agent_system_prompt(env_caps: dict | None = None) -> str:
    """The api arm's system prompt, plus the one line about this environment."""
    return with_agent_tools(system_prompt(), env_caps)


def agent_opening(setup_resp: dict | None = None,
                  env_caps: dict | None = None) -> str:
    """The api arm's first user turn, unchanged. What this environment adds is
    named in the system prompt instead -- see agent_system_prompt()."""
    return default_opening(setup_resp)


# --------------------------------------------------------------- the manifest

class Manifest:
    """What the bench needs to know to run one external agent."""

    def __init__(self, data: dict, base: Path):
        self.base = base
        self.name = str(data.get("name") or base.stem)
        self.command = str(data["command"]).strip()
        self.network = str(data.get("network", "blocked")).lower()
        # shell_env is accepted and ignored: v2 has no host-side shell to
        # point at a sandbox. Left parsed so an old manifest still loads.
        self.shell_env = data.get("shell_env")
        if "command" not in data:
            raise ValueError(f"{base}: manifest has no `command`")

    @staticmethod
    def _search_dirs() -> list[Path]:
        """Where a bare agent name is looked up, most specific first.

        Keeps the bench free of agent code: an agent registers by dropping its
        manifest (or a symlink to it) into one of these, or by pointing
        $FBBENCH_AGENTS at the directory it already lives in.
        """
        dirs: list[Path] = []
        for d in os.environ.get("FBBENCH_AGENTS", "").split(os.pathsep):
            if d.strip():
                dirs.append(Path(d).expanduser())
        dirs.append(Path.home() / ".config" / "fbbench" / "agents")
        dirs.append(Path(__file__).resolve().parents[2] / "agents")
        return dirs

    @classmethod
    def resolve(cls, value: str) -> Path:
        """A path is used as-is; a bare name is found on the search path."""
        p = Path(value).expanduser()
        if p.is_file():
            return p.resolve()
        if "/" not in value and not value.endswith((".yaml", ".yml", ".json")):
            for d in cls._search_dirs():
                for cand in (f"{value}.agent.yaml", f"{value}.agent.yml",
                             f"{value}.yaml", f"{value}.json", f"{value}/agent.yaml"):
                    hit = d / cand
                    if hit.is_file():
                        return hit.resolve()
        raise FileNotFoundError(
            f"no agent manifest for {value!r}. Give a path, or register a name: "
            "put <name>.agent.yaml in ~/.config/fbbench/agents/ (or a dir named "
            "by $FBBENCH_AGENTS).")

    @classmethod
    def load(cls, path: str | Path) -> "Manifest":
        p = cls.resolve(str(path))
        raw = p.read_text()
        try:
            import yaml
            data = yaml.safe_load(raw)
        except Exception:
            data = json.loads(raw)
        if not isinstance(data, dict):
            raise ValueError(f"{p}: manifest must be a mapping")
        return cls(data, p.parent)

    @property
    def allow_network(self) -> bool:
        return self.network in ("allowed", "allow", "on", "true", "1")

    def render(self, **fields) -> str:
        """The command line, with @file references inlined and {fields} filled."""
        cmd = self.command
        # @path -> the file's contents, quoted; resolved next to the manifest.
        out, i = [], 0
        for token in shlex.split(cmd):
            if token.startswith("@"):
                ref = (self.base / token[1:]).resolve()
                out.append(ref.read_text().strip() if ref.is_file() else token)
            else:
                out.append(token)
        rendered = []
        for token in out:
            for k, v in fields.items():
                token = token.replace("{" + k + "}", str(v))
            rendered.append(token)
        return rendered  # a list argv, already split


# ---------------------------------------------------- the challenge container
# There is no host-side sandbox and no staged copy any more. Every agent arm --
# claudecode, codex and any external agent -- drives the SAME per-episode
# mcp-server (fbbench/sweep/mcp_episode.py) inside the challenge image, so the
# tool surface is identical by construction rather than by two implementations
# /challenge onto the host, and the ./submit request bridge) existed only to
# give an external agent a DIFFERENT surface, and that was the asymmetry.
#
# Consequence for an agent: cwd is /challenge and it is read-only; /workspace
# and /tmp are writable; candidates are graded with run_poc_on_harness, not a
# script. Exactly what claudecode has had all along.

_EXEC_MS = re.compile(r"Executed\s+\S+\s+in\s+(\d+)\s*ms")


def _target_ms(verdict: dict) -> str:
    """How long the target itself spent on this input, in its own words.

    libFuzzer prints `Executed <file> in N ms` on every run, and being the
    harness's own clock it excludes the container and grading overhead a
    measurement here would fold in. That distinction is the whole point: the
    signal worth reading is 0 ms (thrown out at the entry gate) against a few
    hundred (the parser actually worked), and on a real challenge the grading
    overhead around a 0 ms run measures 279 ms -- an order of magnitude larger
    than the difference we are trying to show.

    The verdict is flat rather than nested (`stderr` and friends sit at the top
    level, whatever grade_blob's docstring says about `harness_output`), and the
    shape has moved before, so every plausible field is searched.

    Jazzer and other non-libFuzzer harnesses print no such line. There the
    grader's own `duration_ms` is all there is; it is offered under a name that
    says what it measures, because reporting overhead as the target's time would
    be worse than admitting we do not know.
    """
    for key in ("stderr", "stdout", "harness_output", "output"):
        raw = verdict.get(key)
        if not raw:
            continue
        m = _EXEC_MS.search(raw if isinstance(raw, str) else str(raw))
        if m:
            return f"target ran {m.group(1)} ms"
    graded = verdict.get("duration_ms")
    if isinstance(graded, (int, float)):
        return f"graded in {int(graded)} ms (harness clock unavailable)"
    return "target time unknown"


class Judge:
    """The `submit` the agent calls: grades a candidate on the sealed harness,
    returns the verdict live, and remembers every candidate for the score.

    The grader is the bench's own `grade_blob` -- the same one that produces the
    final number -- so the feedback the agent iterates against and the score it
    is given can never diverge.
    """

    def __init__(self, workspace: Path, bug_dir: Path,
                 cell_dir: Path | None = None, preserve_pocs: bool = True,
                 image: str | None = None, header: dict | None = None):
        self.ws = workspace
        self.bug_dir = bug_dir
        self.image = image
        # Graded candidates, filled in after the episode by the same
        # post-hoc pass claudecode and codex use. Nothing is graded during the
        # run any more: the agent calls run_poc_on_harness itself and gets the
        # in-image verdict directly, exactly as the other arms do.
        self.log: list[dict] = []
        self._stop = threading.Event()
        self._t: threading.Thread | None = None
        self._tt: threading.Thread | None = None
        # Live reporting. The api arm flushes every record and copies every
        # agent process exited, so a 30-minute cell was unobservable and a
        # killed one lost everything. Same contract here: one flushed line and
        # one preserved blob per graded candidate, as it happens.
        self.cell_dir = Path(cell_dir) if cell_dir else None
        self.preserve_pocs = preserve_pocs
        self._t0 = time.time()
        self._progress = None
        self._mirrored: dict[str, int] = {}
        # Enough of the run's identity to render a report from a cell that never
        # finished: without it a killed cell's report has no bug, no model and
        # no turn budget, which is most of the header.
        self._header = header or {}

    # progress.jsonl belongs to CandidateLog now: it is the thing that sees a
    # candidate graded. The judge kept an open handle here and never wrote to
    # it, which only risked truncating the observer's file.
    def _open_progress(self) -> None:
        return

    def _open_progress_unused(self) -> None:
        if self.cell_dir is None:
            return
        try:
            self.cell_dir.mkdir(parents=True, exist_ok=True)
            self._progress = (self.cell_dir / "progress.jsonl").open("w", buffering=1)
        except OSError:
            self._progress = None

    # What an agent writes in the workspace, and where it lands in the cell.
    # The workspace is a temp dir that is rmtree'd at the end of a clean run and
    # orphaned in /tmp after a kill, so neither survives as evidence on its own.
    _MIRROR = {".fbagent-trace.jsonl": "trace.jsonl",
               ".fbbench/usage.json": "usage.json"}

    def _mirror(self) -> None:
        """Copy the agent's live files into the cell as they change.

        Without this, a cell killed mid-run keeps its graded candidates but
        loses the reasoning and the spend -- which is the wrong half to lose,
        because the money is already gone. Copy-on-mtime, so the common case is
        two stat() calls per poll.
        """
        if self.cell_dir is None:
            return
        for rel, name in self._MIRROR.items():
            src = self.ws / rel
            try:
                if not src.is_file():
                    continue
                mtime = src.stat().st_mtime_ns
                if self._mirrored.get(rel) == mtime:
                    continue
                shutil.copy2(src, self.cell_dir / name)
                self._mirrored[rel] = mtime
                if name == "trace.jsonl":
                    self._write_live_transcript()
            except OSError:
                pass  # mirroring never breaks grading

    def _write_live_transcript(self) -> None:
        """transcript.jsonl as the run goes, so report.py can render a cell that
        died. No `end` event -- the run has not ended, and claiming otherwise
        would put a terminated_reason on a report for a run still in flight.
        _write_run_artifacts overwrites this with the complete version."""
        recs = _read_trace(self.cell_dir / "trace.jsonl")
        ev = [{"event": "start", "system_prompt": "", "preserve_pocs": self.preserve_pocs,
               "tools": sorted({r.get("tool") for r in recs
                                if r.get("kind") == "tool_call" and r.get("tool")}),
               **self._header}]
        ev += _events_from_trace(recs)
        (self.cell_dir / "transcript.jsonl").write_text(
            "\n".join(json.dumps(e) for e in ev) + "\n")

    def _reported(self) -> dict | None:
        """What the run has spent so far, tokens AND dollars, priced with the
        bench's own table by the same function that prices the final number.

        A run that dies is exactly when this matters: the money is gone and the
        only question left is how much. Reporting tokens and leaving the dollars
        blank asks the reader to price it themselves, and a blank field reads as
        zero to anyone skimming."""
        try:
            raw = json.loads((self.ws / ".fbbench" / "usage.json").read_text())
        except (OSError, ValueError):
            return None
        try:
            priced = price_reported_usage(raw, self._header.get("model", ""))
        except Exception:  # noqa: BLE001 - pricing never breaks grading
            return raw
        return {**priced, "partial": True}

    def _record(self, entry: dict, src: Path, verdict_detail: str) -> None:
        """Persist one graded candidate the moment it is graded. Never raises:
        a reporting failure must not cost the run its grading."""
        if self.cell_dir is None:
            return
        try:
            if self.preserve_pocs and src.is_file():
                sub_d = self.cell_dir / "pocs" / ("crashed" if entry["crashed"] else "clean")
                sub_d.mkdir(parents=True, exist_ok=True)
                shutil.copy(src, sub_d / entry["blob"])
                (sub_d / f"{entry['blob']}.json").write_text(json.dumps({
                    "blob": entry["blob"], "size": entry["size"],
                    "crashed": entry["crashed"],
                    "crash_signature": entry["signature"] or None,
                    "verdict": verdict_detail.strip(),
                    "t": round(time.time() - self._t0, 1),
                }, indent=2))
            if self._progress is not None:
                self._progress.write(json.dumps({
                    "t": round(time.time() - self._t0, 1),
                    "n": len(self.log), "blob": entry["blob"],
                    "size": entry["size"], "crashed": entry["crashed"],
                    "signature": entry["signature"] or None,
                    "verdict": verdict_detail.strip()[:200],
                    "unique_so_far": len(self.signatures()),
                }) + "\n")
                self._progress.flush()
            # A running tally, rewritten each time, so score-so-far is readable
            # without parsing the stream.
            (self.cell_dir / "score.partial.json").write_text(json.dumps({
                **self._header,
                "in_progress": True,
                "elapsed_s": round(time.time() - self._t0, 1),
                "blobs_written": len(self.log),
                "unique_crashes": len(self.signatures()),
                "crash_signatures": sorted(self.signatures()),
                # Spend so far, as the agent last reported it. A run that dies
                # having cost money should say so here rather than leave the
                # reader to guess, and `in_progress: true` is what marks the
                # whole file as a run that never finished.
                "agent_reported": (spend := self._reported()),
                # Lifted to the top level as well, because report.py reads cost
                # from score.total_usd -- nested, a killed cell's report still
                # printed "not reported" over a number that was right there.
                "total_usd": (spend or {}).get("total_usd"),
                "cost_basis": (spend or {}).get("basis"),
            }, indent=2))
        except Exception:  # noqa: BLE001 - reporting never breaks grading
            pass

    # Both are gone: an agent now calls run_poc_on_harness on the same
    # mcp-server every other arm uses, and runs gdb itself inside the
    # container. The judge no longer grades anything during the episode -- it
    # observes, so a killed run still leaves evidence on disk.

    def start(self) -> None:
        self._open_progress()
        self._stop.clear()
        self._t = threading.Thread(target=self._watch, daemon=True)
        self._t.start()

    def _watch(self) -> None:
        """Mirror the agent's own artefacts as it writes them.

        The external arm is the only one that can be killed mid-episode and
        still owe the reader everything it spent. Nothing here touches the
        challenge; it copies what the agent has already written.
        """
        while not self._stop.is_set():
            try:
                self._mirror()
                self._write_live_transcript()
            except Exception:  # noqa: BLE001 - observation never breaks a run
                pass
            self._stop.wait(2.0)

    def stop(self) -> None:
        self._stop.set()
        if self._t is not None:
            self._t.join(timeout=10)
        try:
            self._mirror()
            self._write_live_transcript()
        except Exception:  # noqa: BLE001
            pass
        try:
            if self._progress is not None:
                self._progress.close()
        except Exception:  # noqa: BLE001
            pass

    def signatures(self) -> set[str]:
        return {e["signature"] or "crash|<unnamed>" for e in self.log if e["crashed"]}


# ---------------------------------------------------------------- the cell


def _agent_turns(report: dict | None, ws: Path) -> int:
    """Turns the agent reports, falling back to counting its trace.

    A turn is one model call -- the same unit the api arm bounds with
    `for turn in range(max_turns)` and claudecode passes as --max-turns. An
    agent reports it as `turns` (or the older `steps`) in the summary JSON it
    already prints for cost. Where it reports nothing, the trace's tool_call
    count is a lower bound, not the real figure: a turn may carry several tool
    calls, and one bash call can drive hundreds of submissions."""
    for key in ("turns", "turns_used", "steps"):
        v = (report or {}).get(key)
        if isinstance(v, int) and v >= 0:
            return v
    return _trace_tool_calls(ws)


def _trace_tool_calls(ws: Path) -> int:
    """Tool calls in the agent's own trace -- the fallback for turns."""
    src = ws / ".fbagent-trace.jsonl"
    if not src.is_file():
        return 0
    n = 0
    try:
        for line in src.read_text(errors="replace").splitlines():
            if '"tool_call"' in line:
                n += 1
    except OSError:
        return 0
    return n


def _extract_report(log: str) -> dict | None:
    """The last JSON object an agent printed, if it carries usage or cost.

    Agents already end a run by printing a summary; FuzzingBrain-Agent prints
    {stop_reason, steps, cost_usd, cache_hit_rate, usage:{input, output,
    cache_read, cache_write}}. Reading what an agent already emits beats
    inventing a file for it to write.
    """
    best = None
    for m in re.finditer(r"\{(?:[^{}]|\{[^{}]*\})*\}", log or ""):
        try:
            o = json.loads(m.group(0))
        except ValueError:
            continue
        if isinstance(o, dict) and ("usage" in o or "cost_usd" in o):
            best = o
    return best


def _agent_usage(ws: Path, log: str, model: str) -> dict:
    """Cost for one external-agent cell.

    The bench cannot measure a black-box agent, so cost is knowable only if the
    agent reports it. Two ways, both optional:

      1. the summary JSON it already prints (see _extract_report), or
      2. `.fbbench/usage.json` in the working directory, same field names.

    Tokens are the record; USD is recomputed here with the bench's price table
    so every arm prices identically. An agent's own cost_usd is kept beside it
    as a cross-check, never as the source. An agent that reports nothing is
    costed as UNKNOWN, not zero -- a missing cost must not read as a free run.
    """
    raw = None
    f = ws / ".fbbench" / "usage.json"
    if f.is_file():
        try:
            raw = json.loads(f.read_text())
        except (OSError, ValueError) as e:
            return {"basis": f"unreadable: {e}", "total_usd": None}
    if raw is None:
        raw = _extract_report(log)
    if not raw:
        return {"basis": "unreported", "total_usd": None}

    return price_reported_usage(raw, model)


def price_reported_usage(raw: dict, model: str) -> dict:
    """Turn one agent-reported usage record into tokens + USD.

    The single pricing site. The judge calls it every time it rewrites the
    running tally, so a cell that dies still says what it spent; _agent_usage
    calls it once at the end for the authoritative number. Both go through here
    because two places computing money is how two numbers start disagreeing --
    which was the reason not to price live, and is not a reason to leave the
    field blank. An unfinished run that burned tokens has a cost; refusing to
    name it does not make it smaller.
    """
    u = raw.get("usage") if isinstance(raw.get("usage"), dict) else raw
    def _n(*names):
        for n in names:
            if u.get(n) is not None:
                return int(u[n] or 0)
        return 0
    cr = _n("cache_read", "cache_read_tokens")
    inp = _n("input", "input_tokens")
    if raw.get("input_is_total") or u.get("input_is_total"):
        inp = max(0, inp - cr)
    out_t = _n("output", "output_tokens")
    cw = _n("cache_write", "cache_write_tokens")
    name = raw.get("model") or model
    try:
        rec = cost_usd(name, inp, out_t, cr, cw)
    except Exception:  # noqa: BLE001
        # An --agent cell has no routable model label ("default") -- the model is
        # the agent's business, not the bench's. Unknown price, not an exception.
        rec = {"total_usd": None, "pricing_known": False,
               "note": f"no price for {name!r}"}
    if rec.get("total_usd") is None and isinstance(raw.get("cost_usd"), (int, float)):
        # The bench has no price for this model; the agent priced itself. Use its
        # number, labelled as its number.
        rec["total_usd"] = float(raw["cost_usd"])
        rec["basis"] = "agent-priced"
    rec.update({"basis": rec.get("basis", "agent-reported"),
                "model": raw.get("model") or model,
                "input_tokens": inp, "output_tokens": out_t,
                "cache_read_tokens": cr, "cache_write_tokens": cw,
                "agent_reported_usd": raw.get("cost_usd"),
                "cache_hit_rate": raw.get("cache_hit_rate")})
    return rec



def _events_from_trace(recs: list[dict]) -> list[dict]:
    """The agent's own trace, in report.py's event schema.

    Split out of _write_run_artifacts so the judge can rebuild transcript.jsonl
    as the run goes. The api arm flushes its transcript every record, so a cell
    that dies still renders its dialogue; built only at exit, this arm's report
    came out empty on exactly the runs worth looking at.
    """
    ev: list[dict] = []
    pending: dict[int, list] = {}
    for r in recs:
        step = r.get("step", 0)
        kind = r.get("kind")
        if kind in ("text", "thinking"):
            ev.append({"event": "assistant", "turn": step,
                       "text": r.get("text", ""), "tool_calls": []})
        elif kind == "tool_call":
            tid = f"s{step}-{len(pending.get(step, []))}"
            pending.setdefault(step, []).append(tid)
            ev.append({"event": "assistant", "turn": step, "text": "",
                       "tool_calls": [{"id": tid, "name": r.get("tool", "?"),
                                       "input": r.get("input", {})}]})
        elif kind == "tool_result":
            ids = pending.get(step) or [f"s{step}-0"]
            ev.append({"event": "tool_result", "turn": step,
                       "id": ids.pop(0) if ids else f"s{step}-0",
                       "tool": r.get("tool", "?"),
                       "is_error": bool(r.get("is_error")),
                       "result": r.get("content", r.get("text", ""))})
    return ev


def _read_trace(path: Path) -> list[dict]:
    recs: list[dict] = []
    if not path.is_file():
        return recs
    try:
        for line in path.read_text(errors="ignore").splitlines():
            try:
                recs.append(json.loads(line))
            except ValueError:
                pass
    except OSError:
        pass
    return recs


def _write_run_artifacts(cell_dir: Path, ws: Path, log: str, judge: "Judge",
                         bug: str, model: str, opening: str, *,
                         system_prompt_sent: str = "",
                         score: dict | None = None, usage: dict | None = None,
                         max_turns: int = 0, preserve_pocs: bool = True) -> None:
    """Give an external-agent cell the same paper trail every other arm leaves.

    An episode costs money; it should not end with only a prose log. Copies the
    agent's own step trace out of the workspace (which is deleted next), renders
    it into the transcript schema report.py reads, and writes report.html. An
    agent that leaves no trace still gets a transcript built from its
    submissions, so every cell is browsable.
    """
    # 1. the agent's own trace, before the workspace goes away
    src = ws / ".fbagent-trace.jsonl"
    recs: list[dict] = []
    if src.is_file():
        shutil.copy(src, cell_dir / "trace.jsonl")
    # the verbatim model exchange, if the agent recorded one: the request as it
    # went over the wire, which the transcript does not keep
    exch = ws / ".fbagent-exchange.jsonl"
    if exch.is_file():
        shutil.copy(exch, cell_dir / "exchange.jsonl")
        for line in src.read_text(errors="ignore").splitlines():
            try:
                recs.append(json.loads(line))
            except ValueError:
                pass

    # 2. transcript.jsonl in report.py's event schema
    # report.py reads the header off `start` and `end`, and the distinct-crash
    # table off `unique_crash`. The external arm emitted only a bare `start`, so
    # every field in the header rendered as zero on a cell that had really spent
    # half an hour and a dollar.
    ev: list[dict] = [{"event": "start", "model": model, "bug_id": bug,
                       "system_prompt": system_prompt_sent,
                       "initial_user_message": opening,
                       "max_turns": max_turns, "preserve_pocs": preserve_pocs,
                       "tools": sorted({r.get("tool") for r in (recs or [])
                                        if r.get("kind") == "tool_call"
                                        and r.get("tool")})}]
    if recs:
        ev += _events_from_trace(recs)
    else:
        # No trace: reconstruct what we do know -- every submission and verdict.
        for i, e in enumerate(judge.log):
            ev.append({"event": "assistant", "turn": i, "text": "",
                       "tool_calls": [{"id": f"g{i}", "name": "submit",
                                       "input": {"path": e.get("blob")}}]})
            ev.append({"event": "tool_result", "turn": i, "id": f"g{i}",
                       "tool": "submit", "is_error": False,
                       "result": e.get("detail", "")})
    # One row per distinct fault, in the order the run first saw it.
    seen: set[str] = set()
    for i, e in enumerate(judge.log):
        if not e.get("crashed"):
            continue
        sig = e.get("signature") or "crash|<unnamed>"
        if sig in seen:
            continue
        seen.add(sig)
        ev.append({"event": "unique_crash", "turn": i, "signature": sig,
                   "blob": e.get("blob"), "size": e.get("size")})

    if score is not None:
        u = usage or {}
        ev.append({"event": "end",
                   "terminated_reason": score.get("terminated_reason"),
                   "unique_crashes": score.get("unique_crashes"),
                   "crash_signatures": score.get("crash_signatures"),
                   "turns_used": score.get("turns_used"),
                   "duration_s": score.get("duration_s"),
                   "input_tokens": u.get("input_tokens", 0),
                   "output_tokens": u.get("output_tokens", 0),
                   "cache_read_tokens": u.get("cache_read_tokens", 0),
                   "cache_write_tokens": u.get("cache_write_tokens", 0),
                   "total_usd": score.get("total_usd"),
                   "cost_basis": score.get("cost_basis"),
                   "grading": score.get("grading"),
                   "blobs_written": score.get("blobs_written")})

    (cell_dir / "transcript.jsonl").write_text(
        "\n".join(json.dumps(e) for e in ev) + "\n")

    # 3. report.html
    try:
        from fbbench.runner.report import write_report
        write_report(cell_dir)
    except Exception as e:  # noqa: BLE001
        print(f"  note: report.html skipped: {e}", flush=True)


def _kill_pg(proc: subprocess.Popen) -> None:
    """SIGKILL the child's whole process group, falling back to the child."""
    try:
        os.killpg(os.getpgid(proc.pid), signal.SIGKILL)
    except Exception:  # noqa: BLE001
        try:
            proc.kill()
        except Exception:  # noqa: BLE001
            pass


def _run_agent(argv: list[str], cwd: str, env: dict, timeout_s: int,
               log_path: Path, spend: "Callable[[], float | None] | None" = None,
               usd_cap: float = AGENT_USD_CAP) -> tuple[str, bool | str]:
    """Run the agent under a HARD wall clock of exactly `timeout_s`.

    The other arms get no grace: claudecode hard-kills `claude -p` on its
    t0+timeout_s watchdog, and the api episode checks the same deadline between
    turns and stops itself (its orchestrator backstop is writeout headroom the
    loop can never spend). This arm used to allow timeout_s+300 before the kill,
    which is 300 seconds of real working time nobody else has -- an agent that
    ignores the {timeout} it was handed simply kept going. Killing on the second
    costs nothing now: the judge persists every candidate as it grades it, and
    turns fall back to the trace when the agent never printed its report.

    The child gets its own process group so the kill takes its descendants with
    it. `subprocess.run(timeout=...)` kills only the direct child, so a docker
    or gdb grandchild would hold the pipe open and hang the cell past its budget.

    Output goes STRAIGHT TO `log_path`, not to a pipe we read at the end. The
    api arm flushes its dialogue every record, so a cell that dies -- the host
    going down, the sweep being SIGKILLed, a dropped connection -- still shows
    what the run had done and what it had spent. Captured at exit, an external
    agent's log is held in a pipe that dies with the process: exactly the case
    where the money is already gone and the evidence is what is left.

    stderr is merged into the same file rather than kept apart, so the two
    interleave in real time; concatenating them afterwards loses which output
    came before which error.

    Returns (log_text, timed_out).
    """
    log_path.parent.mkdir(parents=True, exist_ok=True)
    with log_path.open("w", buffering=1) as fh:
        proc = subprocess.Popen(argv, cwd=cwd, env=env, stdin=subprocess.DEVNULL,
                                stdout=fh, stderr=subprocess.STDOUT,
                                text=True, start_new_session=True)
        deadline = time.time() + timeout_s
        timed_out: bool | str = False
        try:
            while True:
                left = deadline - time.time()
                if left <= 0:
                    _kill_pg(proc); proc.wait(timeout=30); timed_out = True
                    break
                try:
                    # Poll rather than one long wait, so the dollar cap can be
                    # checked while the agent is still spending. Reading what the
                    # agent reports is the only cost signal this arm has; an
                    # agent that reports nothing is bounded by the clock alone.
                    proc.wait(timeout=min(left, 10))
                    break
                except subprocess.TimeoutExpired:
                    pass
                if spend is not None and usd_cap:
                    now = spend()
                    if now is not None and now >= usd_cap:
                        _kill_pg(proc); proc.wait(timeout=30)
                        timed_out = "cost-cap"
                        break
        except BaseException:                  # Ctrl-C / SIGTERM handler
            _kill_pg(proc)
            raise
    try:
        return log_path.read_text(errors="replace"), timed_out
    except OSError:
        return "", timed_out


def run_cell(cell_dir: Path, bug: str, model: str, timeout_s: int,
             max_turns: int = 100, *, manifest: Manifest, api_key: str | None = None,
             preserve_pocs: bool = True) -> dict | None:
    """Stage a challenge, run the external agent over it, grade what it left."""
    cell_dir = Path(cell_dir)
    # What a reader sees: <agent>-<model>, as claudecode and codex label theirs.
    # `model` itself stays the raw id the agent is invoked with.
    label = f"{manifest.name}-{model}" if getattr(manifest, "name", "") else model
    real = find_bug(bug)
    if not real:
        return {"error": f"bug not found: {bug}"}
    alias = _full_scan_alias(str(real))
    # the AGENT image set: same challenge, with gdb and a readable target
    image = agent_image(alias)

    root = Path(tempfile.mkdtemp(prefix=f"ext-{alias}-"))
    ws = root / "workspace"
    ws.mkdir(parents=True, exist_ok=True)
    server = None
    try:

        # The SAME per-episode mcp-server every other agent arm drives. The
        # agent speaks MCP to it over `relay.py`; cwd inside is /challenge
        # (read-only), /workspace is the bind-mounted dir above.
        candidates = CandidateLog(cell_dir, str(ws), preserve=preserve_pocs)
        server, sock_path, relay_path, _srv = _start_episode_server(
            image, str(ws), str(root), candidates)
        sandbox_kind = "container"
        # The api arm builds its first user turn from setup(), so the server has
        # to be up before the opening exists -- and therefore before the
        # transcript header that records it.
        setup_resp = fetch_setup(sock_path)
        # what this container actually offers, rather than what we assume
        env_caps = probe_environment(sock_path)
        opening = agent_opening(setup_resp, env_caps)

        judge = Judge(ws, Path(real), cell_dir=cell_dir, preserve_pocs=preserve_pocs,
                      image=image,
                      header={"bug_id": bug, "model": label, "max_turns": max_turns,
                              "initial_user_message": opening,
                              "system_prompt": agent_system_prompt(env_caps)})
        judge.start()

        # Every arm is budgeted the same way: a turn cap and a wall clock, and
        # no dollar cap (the api arm has none, so neither may we). The api arm
        # owns its loop and bounds it directly; claudecode passes --max-turns to
        # the CLI and trusts it to obey. An external agent is the same shape as
        # claudecode -- a black box we cannot count model calls inside -- so it
        # gets the same contract: the budget is handed over as {max_turns} and
        # the agent must honour it and report turns_used in its summary. A
        # manifest that ignores {max_turns} is running unbudgeted, and the
        # turn_budget_honoured field in score.json says so. The wall clock is
        # the half we CAN enforce, and _run_agent enforces it on the second.
        # {model} is the arm's model, the same string the api arm instantiates
        # and claudecode passes to `claude --model`. Without it an external
        # manifest has to hardcode one, so `--model` on the command line would
        # silently not reach the agent and every cell in a sweep would run
        # whatever the manifest said -- the run would be mislabelled, not fail.
        argv = manifest.render(workspace=str(ws), timeout=str(timeout_s),
                               opening=opening,
                               mcp_socket=sock_path, relay=relay_path,
                               max_turns=str(max_turns), model=model)
        env = dict(os.environ)
        # The manifest's own directory goes on PYTHONPATH, so a Python agent can
        # `python3 -m its_package.run` from the staged workspace without knowing
        # an absolute path. Harmless to agents that do not import anything.
        env["PYTHONPATH"] = os.pathsep.join(
            p for p in (str(manifest.base), env.get("PYTHONPATH", "")) if p)
        # How an agent reaches the bench tools, for a manifest that would rather
        # read them from the environment than from its command template.
        env["FBBENCH_MCP_SOCKET"] = sock_path
        # The api arm's SYSTEM prompt, in the system slot rather than folded
        # into the first user turn. An agent that ignores it is no worse off
        # than before; one that reads it now matches the baseline's structure.
        env["FBBENCH_SYSTEM_PROMPT"] = agent_system_prompt(env_caps)
        env["FBBENCH_MCP_RELAY"] = relay_path
        if api_key:
            env["ANTHROPIC_API_KEY"] = api_key

        started = time.time()
        terminated = "done"
        interrupted = False

        # below is written only after the agent exits, and the `finally` clause
        # then rmtree's the workspace. One terminated libpng-01 run lost 236
        # graded candidates and its cost that way. The work is real and already
        # on disk -- the judge graded every blob as it was submitted -- so treat
        # an interrupt like the wall-clock case: fall through, persist the cell,
        # and only then re-raise so the matrix still stops.
        def _on_term(_signum, _frame):
            raise KeyboardInterrupt
        try:
            prev_term = signal.signal(signal.SIGTERM, _on_term)
        except (ValueError, OSError):   # not the main thread
            prev_term = None
        cell_dir.mkdir(parents=True, exist_ok=True)
        agent_log = cell_dir / "agent.log"
        try:
            log, timed_out = _run_agent(
                argv, str(ws), env, min(timeout_s, AGENT_WALL_CAP_S), agent_log,
                spend=lambda: (judge._reported() or {}).get("total_usd"))
            if timed_out == "cost-cap":
                terminated = "cost-cap"
            elif timed_out:
                terminated = "wall-clock"
        except KeyboardInterrupt:
            # _run_agent kills the group and re-raises. The log is on disk
            # either way now, so read back what the agent had printed.
            terminated = "interrupted"
            log = agent_log.read_text(errors="replace") if agent_log.is_file() else ""
            interrupted = True
        finally:
            if prev_term is not None:
                try:
                    signal.signal(signal.SIGTERM, prev_term)
                except (ValueError, OSError):
                    pass
        duration = time.time() - started
        judge.stop()

        # agent.log is already on disk -- _run_agent wrote it as the agent ran.
        # Rewriting it here would only risk replacing a complete log with a
        # truncated re-read on the one path where it matters.
        #
        # PoCs are not copied here any more. CandidateLog wrote each one as the
        # agent graded it, and _crash_signatures writes them again below; the
        # with the request bridge, so it would have raised on the first run.
        try:
            usage = _agent_usage(ws, log, model)
        except Exception as e:  # noqa: BLE001
            usage = {"basis": f"cost failed: {type(e).__name__}", "total_usd": None}
        # Turns come from the same summary JSON the agent prints for cost.
        turns_used = _agent_turns(_extract_report(log), ws)
        # Graded exactly the way claudecode and codex are graded: every
        # candidate the agent left in /workspace, run once through the image's
        # own harness after the episode. Same helper, same heuristic, same
        # in-image grader -- so three arms cannot report numbers that diverge
        # for a reason no one can see.
        # What the agent SUBMITTED, seen live on the relay -- not whatever it
        # left in the workspace. A workspace sweep grades `gen.py` as a PoC and
        # charges three in-image rounds for the privilege.
        candidates.close()
        blobs = candidates.host_blobs()
        pocs_dir = str(cell_dir / "pocs") if preserve_pocs else None
        sigs, best = _crash_signatures(Path(real), blobs, pocs_dir)
        # Per-candidate crashed/clean comes from the live verdicts, not from
        # `b == best`: several candidates can crash, and marking only the first
        # would understate every summary row built from this.
        _seen = {e["path"].rsplit("/", 1)[-1]: e for e in candidates.entries}
        judge.log = [{"blob": os.path.basename(b),
                      "crashed": bool(_seen.get(os.path.basename(b), {}).get("crashed")),
                      "signature": _seen.get(os.path.basename(b), {}).get("signature")}
                     for b in blobs]
        if best and Path(best).is_file():
            shutil.copy(best, cell_dir / "best_blob")

        score = {
            "bug_id": bug, "model": label, "seed": 0,
            "unique_crashes": len(sigs), "crash_signatures": sorted(sigs),
            "score": len(sigs), "grading": "in-image",
            "terminated_reason": (terminated if blobs else
                                  f"{terminated}: agent submitted nothing"),
            "duration_s": round(duration, 1),
            "turns_used": turns_used,
            "turn_budget_honoured": turns_used <= max_turns,
            "blobs_written": len(blobs), "max_turns": max_turns,
            # report.py reads mode/grading/preserve-PoCs out of `config`, the
            # same shape the api arm writes. Without it a cell renders as
            # "grading not recorded" whatever it actually did.
            "config": {
                "mode": "blind",
                "max_turns": max_turns,
                "timeout_s": timeout_s,
                "stop_on_crash": False,
                "preserve_pocs": preserve_pocs,
                "grading": "in-image",
                "image": image,
                "agent": manifest.name,
                "sandbox": sandbox_kind,
            },
            "agent": manifest.name,
            # Screened, not assumed: a result should be readable knowing whether
            # the agent reached for a fuzzer. Zero is the expected value; a
            # nonzero one is not a disqualification, it is information.
            "fuzzing_attempts": len(candidates.blocked),
            # What this arm had that the api arm does not. A result should be
            # readable knowing which tools were on PATH when it was produced.
            "arm": f"external:{manifest.name}" if getattr(manifest, "name", "") else "external",
            "agent_image": image,
            "agent_image_digest": image_digest(image),
            "network": "allowed" if manifest.allow_network else "blocked",
            "sandbox": sandbox_kind,
            "tokens_used": (usage.get("input_tokens", 0)
                            + usage.get("output_tokens", 0)) or None,
            "total_usd": usage.get("total_usd"),
            "cost_basis": usage.get("basis"),
        }
        # The score goes down first: nothing after the agent exits is worth
        # losing a completed run over.
        (cell_dir / "score.json").write_text(json.dumps(score, indent=2))
        # Only now can the report be rendered: its header is the run's cost,
        # duration, turn count and grading, and none of that existed until the
        # score was built. Rendering it earlier is why every external cell's
        # report read "0 turns used, $0.0000, duration 0.0s".

        # The running tally has done its job; score.json is authoritative and
        # two files claiming to be the score is how a reader gets misled.
        (cell_dir / "score.partial.json").unlink(missing_ok=True)
        (cell_dir / "cost.json").write_text(json.dumps(
            {**usage, "agent": manifest.name,
             "pricing_source": f"external:{usage.get('basis')}"}, indent=2))
        # Only now can the report render: its header is read straight out of
        # existed -- which is why every external cell read "0 turns used,
        # $0.0000, duration 0.0s" over a real half-hour run.
        _write_run_artifacts(cell_dir, ws, log, judge, bug, model, opening,
                             system_prompt_sent=agent_system_prompt(env_caps),
                             score=score, usage=usage,
                             max_turns=max_turns, preserve_pocs=preserve_pocs)
        if interrupted:
            # The cell is on disk now; let the interrupt do its job.
            print(f"  interrupted: cell persisted to {cell_dir}", flush=True)
            raise KeyboardInterrupt
        return score
    finally:
        if server is not None:
            try:
                server.terminate()
                server.wait(timeout=15)
            except Exception:  # noqa: BLE001
                try: server.kill()
                except Exception: pass
        shutil.rmtree(root, ignore_errors=True)


if __name__ == "__main__":
    import sys
    sys.exit("the external arm has no standalone CLI.\n"
             "use:  fb-bench run <bugs> --agent path/to/agent.yaml")
