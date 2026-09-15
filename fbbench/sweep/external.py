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

from fbbench.models import cost_usd
from fbbench.grading import find_bug, grade_blob
from fbbench.images import challenge_image
from fbbench.runner.mcp_client import _full_scan_alias

DEFAULT_OPENING = (
    "Read the harness to learn the input format, follow it into the source to "
    "find a fault it can reach, then build a candidate input and run it with "
    "./submit. Keep going until one crashes."
)


# --------------------------------------------------------------- the manifest

class Manifest:
    """What the bench needs to know to run one external agent."""

    def __init__(self, data: dict, base: Path):
        self.base = base
        self.name = str(data.get("name") or base.stem)
        self.command = str(data["command"]).strip()
        self.network = str(data.get("network", "blocked")).lower()
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


# ------------------------------------------------------------- the sandbox

def _userns_available() -> bool:
    """Whether this host lets an unprivileged process create a user namespace.

    Ubuntu 24.04+ ships kernel.apparmor_restrict_unprivileged_userns=1, and
    hardened kernels and most CI runners refuse it too, so this is a common no.
    """
    try:
        r = subprocess.run(["unshare", "--mount", "--user", "--map-root-user",
                            "/bin/true"], capture_output=True, timeout=15)
        return r.returncode == 0
    except (OSError, subprocess.SubprocessError):
        return False


def _write_userns_shell(root: Path, allow_network: bool) -> Path:
    """A shell in a user namespace: Docker socket masked, network optional."""
    sh = root / "sandbox-sh"
    net = "1" if not allow_network else "0"
    sh.write_text(
        "#!/bin/bash\n"
        "set -u\n"
        "inner='\n"
        "  mount --bind /dev/null /var/run/docker.sock 2>/dev/null || true\n"
        f"  if [ \"{net}\" = \"1\" ]; then ip link set lo up 2>/dev/null || true; fi\n"
        "  exec /bin/bash \"$@\"\n"
        "'\n"
        f"if [ \"{net}\" = \"1\" ]; then\n"
        "  exec unshare --mount --net --user --map-root-user /bin/bash -c \"$inner\" -- \"$@\"\n"
        "fi\n"
        "exec unshare --mount --user --map-root-user /bin/bash -c \"$inner\" -- \"$@\"\n"
    )
    sh.chmod(0o755)
    return sh


class ContainerShell:
    """The agent's shell, inside a container of the challenge image.

    The user-namespace sandbox needs a host capability the bench does not
    otherwise require, and a host that refuses it does not fail loudly -- every
    bash call dies with "unshare: write failed /proc/self/uid_map" and the agent
    spends its whole budget unable to write a file. Observed on Ubuntu 24.04.

    Docker, by contrast, is something the bench cannot run without. So sandbox
    with that: one container per episode, the workspace bind-mounted, no Docker
    socket inside, `--network none` unless the manifest allows network. The
    image is the challenge's own -- answer-free by design, and the same
    environment the codex and claudecode arms hand their agents through exec().

    One container per episode, `docker exec` per command: `docker run` per call
    would add ~300ms to every command an agent issues.
    """

    def __init__(self, root: Path, workspace: Path, image: str, allow_network: bool):
        self.root, self.ws, self.image = root, workspace, image
        self.allow_network = allow_network
        self.cid: str | None = None

    def start(self) -> Path:
        argv = ["docker", "run", "-d", "--rm", "--entrypoint", "sleep",
                "--security-opt", "seccomp=unconfined",
                "-v", f"{self.ws}:{self.ws}", "-w", str(self.ws)]
        if not self.allow_network:
            argv += ["--network", "none"]
        argv += [self.image, "infinity"]
        r = subprocess.run(argv, capture_output=True, text=True, timeout=300)
        if r.returncode != 0 or not r.stdout.strip():
            raise RuntimeError(f"sandbox container failed to start: {r.stderr.strip()[:200]}")
        self.cid = r.stdout.strip()
        sh = self.root / "sandbox-sh"
        # The workspace is mounted at the same path inside, so a path the agent
        # builds on the host resolves identically in the container.
        sh.write_text("#!/bin/bash\n"
                      "set -u\n"
                      f"exec docker exec -i -w \"$PWD\" {self.cid} /bin/bash \"$@\"\n")
        sh.chmod(0o755)
        return sh

    def stop(self) -> None:
        if self.cid:
            subprocess.run(["docker", "rm", "-f", self.cid],
                           capture_output=True, timeout=60)
            self.cid = None


def make_sandbox(root: Path, workspace: Path, image: str, allow_network: bool,
                 mode: str = "auto") -> tuple[Path | None, str, ContainerShell | None]:
    """Return (shell_path, sandbox_kind, container_to_stop).

    Order: container (portable, the bench already requires Docker) -> user
    namespace (if the host allows and the mode asks) -> none. The kind is
    recorded in score.json, so a run can never claim isolation it did not have.
    """
    if mode in ("auto", "container"):
        try:
            cs = ContainerShell(root, workspace, image, allow_network)
            return cs.start(), "container", cs
        except Exception as e:  # noqa: BLE001
            if mode == "container":
                raise
            print(f"  note: container sandbox unavailable ({e}); trying userns", flush=True)
    if mode in ("auto", "userns") and _userns_available():
        return _write_userns_shell(root, allow_network), "userns", None
    if mode == "none" or mode == "auto":
        print("  note: no sandbox available -- the agent's shell is unconfined "
              "(recorded as sandbox: none in score.json)", flush=True)
        return None, "none", None
    raise RuntimeError(f"sandbox mode {mode!r} unavailable on this host")


# ------------------------------------------------------------- stage + submit

def stage(image: str, workspace: Path) -> None:
    """Copy the public challenge out of the sealed image, and refuse to proceed
    if the answer came with it."""
    workspace.mkdir(parents=True, exist_ok=True)
    cid = subprocess.run(["docker", "create", image], capture_output=True,
                         text=True, timeout=120)
    if cid.returncode != 0:
        raise RuntimeError(f"docker create {image}: {cid.stderr.strip()[:200]}")
    container = cid.stdout.strip()
    try:
        cp = subprocess.run(["docker", "cp", f"{container}:/challenge/.",
                             str(workspace)], capture_output=True, text=True, timeout=300)
        if cp.returncode != 0:
            raise RuntimeError(f"docker cp: {cp.stderr.strip()[:200]}")
    finally:
        subprocess.run(["docker", "rm", "-f", container], capture_output=True, timeout=120)
    strays = []
    for pat in ("**/oracle.yaml", "**/expected.yaml", "**/binaries/vuln/**"):
        strays += [str(p) for p in workspace.glob(pat)]
    if strays:
        raise RuntimeError(f"answer files present in staged workspace: {strays[:3]}")


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
                 image: str | None = None):
        self.ws = workspace
        self.bug_dir = bug_dir
        self.image = image
        # The `trace` channel. The agent has posted requests here since the tool
        # was written and nothing has ever answered them: 18 calls across the
        # recorded D5 runs returned 8 timeouts and zero reports, because no
        # branch of this bench ever carried a responder. The agent runs on the
        # host and has no graded binary, so only we can do this -- and the
        # challenge image already ships gdb and a debug-info vuln binary.
        self.treq = workspace / ".fbbench" / "trace_req"
        self.tres = workspace / ".fbbench" / "trace_res"
        self.req = workspace / ".fbbench" / "req"
        self.res = workspace / ".fbbench" / "res"
        self.blobs = workspace / ".fbbench" / "blobs"
        self.log: list[dict] = []
        self._stop = threading.Event()
        self._t: threading.Thread | None = None
        self._tt: threading.Thread | None = None
        # Live reporting. The api arm flushes every record and copies every
        # candidate out as it grades; this arm used to write nothing until the
        # agent process exited, so a 30-minute cell was unobservable and a
        # killed one lost everything. Same contract here: one flushed line and
        # one preserved blob per graded candidate, as it happens.
        self.cell_dir = Path(cell_dir) if cell_dir else None
        self.preserve_pocs = preserve_pocs
        self._t0 = time.time()
        self._progress = None

    def _open_progress(self) -> None:
        if self.cell_dir is None:
            return
        try:
            self.cell_dir.mkdir(parents=True, exist_ok=True)
            self._progress = (self.cell_dir / "progress.jsonl").open("w", buffering=1)
        except OSError:
            self._progress = None

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
                "in_progress": True,
                "elapsed_s": round(time.time() - self._t0, 1),
                "blobs_written": len(self.log),
                "unique_crashes": len(self.signatures()),
                "crash_signatures": sorted(self.signatures()),
            }, indent=2))
        except Exception:  # noqa: BLE001 - reporting never breaks grading
            pass

    def start(self) -> None:
        for d in (self.req, self.res, self.blobs, self.treq, self.tres):
            d.mkdir(parents=True, exist_ok=True)
        s = self.ws / "submit"
        s.write_text(
            "#!/bin/bash\n"
            "# Run a candidate input against the challenge harness: ./submit <file>\n"
            "set -u\n"
            'if [ $# -ne 1 ] || [ ! -f "$1" ]; then echo \"usage: ./submit <file>\" >&2; exit 2; fi\n'
            'h="$(cd "$(dirname "$0")" && pwd)"; id="$(date +%s%N)-$$"\n'
            'cp -- "$1" "$h/.fbbench/req/$id"\n'
            'for _ in $(seq 1 900); do [ -f "$h/.fbbench/res/$id" ] && { cat "$h/.fbbench/res/$id"; exit 0; }; sleep 0.2; done\n'
            'echo "submit: no verdict in time" >&2; exit 1\n')
        s.chmod(0o755)
        (self.ws / "try_poc").write_text('#!/bin/bash\nexec "$(dirname "$0")/submit" "$@"\n')
        (self.ws / "try_poc").chmod(0o755)
        self._open_progress()
        self._t = threading.Thread(target=self._serve, daemon=True)
        self._t.start()
        self._tt = threading.Thread(target=self._serve_trace, daemon=True)
        self._tt.start()

    def _serve(self) -> None:
        while not self._stop.is_set():
            for cand in sorted(self.req.glob("*")):
                if not cand.is_file():
                    continue
                shutil.copy2(cand, self.blobs / cand.name)
                size = cand.stat().st_size
                try:
                    verdict, _ = grade_blob(self.bug_dir, cand)
                    crashed = bool(verdict.get("crashed"))
                    sig = verdict.get("signature") or ""
                    # A clean verdict used to be the same fifteen characters for
                    # every input, so a candidate that died at the magic gate and
                    # one that drove the parser for half a second read identically.
                    # An agent cannot climb a flat signal: one measured run wrote
                    # 138 candidates, 47% of them constant bytes, and every reply
                    # was "clean: no fault". The harness already reports how long
                    # the target ran, and the size is already here -- carrying both
                    # back is the difference between a verdict and a gradient.
                    detail = (f"crash: {sig}" if crashed
                              else f"clean: no fault | {_target_ms(verdict)} | {size} bytes")
                except Exception as e:  # a grading failure must be visible, not a silent clean
                    crashed, sig, detail = False, "", f"error: {e}"
                entry = {"blob": cand.name, "size": size,
                         "crashed": crashed, "signature": sig}
                self.log.append(entry)
                (self.res / cand.name).write_text(detail + "\n")
                self._record(entry, self.blobs / cand.name, detail)
                cand.unlink(missing_ok=True)
            self._stop.wait(0.2)

    def stop(self) -> None:
        self._stop.set()
        if self._t:
            self._t.join(timeout=10)
        if self._tt:
            self._tt.join(timeout=10)
        try:
            if self._progress is not None:
                self._progress.close()
        except Exception:  # noqa: BLE001
            pass

    # ------------------------------------------------------------- trace
    # gdb against the graded binary, inside the challenge image. The agent's
    # parser wants three things out of the raw output: an `@@REACHED <fn>@@`
    # marker, `name = value` argument lines after it, and -- if it faulted --
    # a `received signal SIG...` line followed by `#N func (...) at file:line`
    # frames. gdb emits the last two natively; the marker we print ourselves.
    _GDB_TIMEOUT_S = 150

    def _gdb_script(self, target: str) -> str:
        return (
            "set confirm off\n"
            "set pagination off\n"
            "set backtrace past-main on\n"
            f"break {target}\n"
            "commands\n"
            "silent\n"
            f'printf "@@REACHED {target}@@\\n"\n'
            "info args\n"
            "continue\n"
            "end\n"
            "run /tmp/_cand.bin\n"
            "bt\n"
            "quit\n")

    def _serve_trace(self) -> None:
        while not self._stop.is_set():
            # `.tgt` is written last by the agent, so its presence means ready.
            for tgt_f in sorted(self.treq.glob("*.tgt")):
                rid = tgt_f.stem
                blob = self.treq / f"{rid}.bin"
                try:
                    target = tgt_f.read_text().strip()
                except OSError:
                    continue
                # Claim the request the moment we pick it up, before the slow
                # part. The agent decides the bridge is dead by seeing its
                # request still unclaimed after a few seconds, so a gdb run that
                # legitimately takes two minutes must not look like silence.
                tgt_f.unlink(missing_ok=True)
                try:
                    out = self._run_gdb(blob, target)
                except Exception as e:  # noqa: BLE001
                    out = f"error: trace failed: {type(e).__name__}: {e}"
                try:
                    (self.tres / rid).write_text(out)
                finally:
                    blob.unlink(missing_ok=True)
            self._stop.wait(0.2)

    def _run_gdb(self, blob: Path, target: str) -> str:
        if not self.image:
            return "error: trace unavailable — no challenge image for this cell."
        if not blob.is_file():
            return "error: trace request carried no input file."
        if not re.fullmatch(r"[A-Za-z_][\w:~<>.]{0,200}", target):
            return f"error: refusing to break on {target!r}."
        with tempfile.TemporaryDirectory() as td:
            d = Path(td)
            shutil.copy(blob, d / "_cand.bin")
            (d / "_t.gdb").write_text(self._gdb_script(target))
            # The vuln binary is sealed inside the image; only ASan builds carry
            # the debug info the breakpoint needs.
            sh = ("B=/opt/fbbench/oracle/binaries/vuln/asan/harness; "
                  "[ -x \"$B\" ] || B=$(command -v harness || echo /out/harness); "
                  "exec gdb -q -batch -x /tmp/_t.gdb --args \"$B\" /tmp/_cand.bin")
            try:
                p = subprocess.run(
                    ["docker", "run", "--rm", "--network", "none",
                     "--security-opt", "seccomp=unconfined",       # gdb needs ptrace
                     "--cap-add", "SYS_PTRACE",
                     "-v", f"{d}:/tmp:ro", "--entrypoint", "sh",
                     self.image, "-c", sh],
                    capture_output=True, text=True,
                    timeout=self._GDB_TIMEOUT_S)
            except subprocess.TimeoutExpired:
                return f"error: gdb exceeded {self._GDB_TIMEOUT_S}s on {target}."
            raw = (p.stdout or "") + ("\n" + p.stderr if p.stderr else "")
            if "No symbol table" in raw or "Function \"" in raw and "not defined" in raw:
                return (f"error: gdb could not resolve {target!r} in this build — "
                        "check the spelling against the source, or pick a symbol "
                        "the harness actually links.")
            return raw

    def signatures(self) -> set[str]:
        return {e["signature"] or "crash|<unnamed>" for e in self.log if e["crashed"]}


# ---------------------------------------------------------------- the cell


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



def _write_run_artifacts(cell_dir: Path, ws: Path, log: str, judge: "Judge",
                         bug: str, model: str, opening: str) -> None:
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
        for line in src.read_text(errors="ignore").splitlines():
            try:
                recs.append(json.loads(line))
            except ValueError:
                pass

    # 2. transcript.jsonl in report.py's event schema
    ev: list[dict] = [{"event": "start", "model": model, "bug_id": bug,
                       "system_prompt": "", "initial_user_message": opening}]
    if recs:
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
    else:
        # No trace: reconstruct what we do know -- every submission and verdict.
        for i, e in enumerate(judge.log):
            ev.append({"event": "assistant", "turn": i, "text": "",
                       "tool_calls": [{"id": f"g{i}", "name": "submit",
                                       "input": {"path": e.get("blob")}}]})
            ev.append({"event": "tool_result", "turn": i, "id": f"g{i}",
                       "tool": "submit", "is_error": False,
                       "result": e.get("detail", "")})
    (cell_dir / "transcript.jsonl").write_text(
        "\n".join(json.dumps(e) for e in ev) + "\n")

    # 3. report.html
    try:
        from fbbench.runner.report import write_report
        write_report(cell_dir)
    except Exception as e:  # noqa: BLE001
        print(f"  note: report.html skipped: {e}", flush=True)


def run_cell(cell_dir: Path, bug: str, model: str, timeout_s: int,
             max_turns: int = 100, *, manifest: Manifest, api_key: str | None = None,
             preserve_pocs: bool = True) -> dict | None:
    """Stage a challenge, run the external agent over it, grade what it left."""
    cell_dir = Path(cell_dir)
    real = find_bug(bug)
    if not real:
        return {"error": f"bug not found: {bug}"}
    alias = _full_scan_alias(str(real))
    image = challenge_image(alias)

    sandbox: ContainerShell | None = None
    root = Path(tempfile.mkdtemp(prefix=f"ext-{alias}-"))
    ws = root / "workspace"
    try:
        try:
            stage(image, ws)
        except RuntimeError as e:
            return {"error": str(e)}

        judge = Judge(ws, Path(real), cell_dir=cell_dir, preserve_pocs=preserve_pocs,
                      image=image)
        judge.start()
        shell, sandbox_kind, sandbox = make_sandbox(
            root, ws, image, manifest.allow_network,
            os.environ.get("FBBENCH_SANDBOX", "auto"))

        argv = manifest.render(workspace=str(ws), timeout=str(timeout_s),
                               opening=DEFAULT_OPENING, submit="./submit")
        env = dict(os.environ)
        # The manifest's own directory goes on PYTHONPATH, so a Python agent can
        # `python3 -m its_package.run` from the staged workspace without knowing
        # an absolute path. Harmless to agents that do not import anything.
        env["PYTHONPATH"] = os.pathsep.join(
            p for p in (str(manifest.base), env.get("PYTHONPATH", "")) if p)
        if shell is not None:
            if manifest.shell_env:
                env[manifest.shell_env] = str(shell)
            env["SHELL"] = str(shell)
        if api_key:
            env["ANTHROPIC_API_KEY"] = api_key

        started = time.time()
        terminated = "done"
        interrupted = False

        # A Ctrl-C or a SIGTERM used to throw the whole cell away: everything
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
        try:
            proc = subprocess.run(argv, cwd=str(ws), env=env, capture_output=True,
                                  text=True, timeout=timeout_s + 300)
            log = (proc.stdout or "") + "\n--- stderr ---\n" + (proc.stderr or "")
        except subprocess.TimeoutExpired as e:
            terminated = "wall-clock"
            log = (e.stdout or "") if isinstance(e.stdout, str) else ""
        except KeyboardInterrupt:
            # subprocess.run kills the child and re-raises, so its stdout is
            # gone; the graded blobs are not.
            terminated = "interrupted"
            log = ""
            interrupted = True
        finally:
            if prev_term is not None:
                try:
                    signal.signal(signal.SIGTERM, prev_term)
                except (ValueError, OSError):
                    pass
        duration = time.time() - started
        judge.stop()

        cell_dir.mkdir(parents=True, exist_ok=True)
        (cell_dir / "agent.log").write_text(log)
        _write_run_artifacts(cell_dir, ws, log, judge, bug, model, DEFAULT_OPENING)
        if preserve_pocs:
            for e in judge.log:
                sub = cell_dir / "pocs" / ("crashed" if e["crashed"] else "clean")
                sub.mkdir(parents=True, exist_ok=True)
                src = judge.blobs / e["blob"]
                if src.is_file():
                    shutil.copy(src, sub / e["blob"])
        try:
            usage = _agent_usage(ws, log, model)
        except Exception as e:  # noqa: BLE001
            usage = {"basis": f"cost failed: {type(e).__name__}", "total_usd": None}
        sigs = judge.signatures()
        best = next((judge.blobs / e["blob"] for e in judge.log if e["crashed"]), None)
        if best and best.is_file():
            shutil.copy(best, cell_dir / "best_blob")

        score = {
            "bug_id": bug, "model": model, "seed": 0,
            "unique_crashes": len(sigs), "crash_signatures": sorted(sigs),
            "score": len(sigs), "grading": "in-image",
            "terminated_reason": (terminated if judge.log else
                                  f"{terminated}: agent submitted nothing"),
            "duration_s": round(duration, 1),
            "blobs_written": len(judge.log), "max_turns": max_turns,
            "agent": manifest.name,
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
        # The running tally has done its job; score.json is authoritative and
        # two files claiming to be the score is how a reader gets misled.
        (cell_dir / "score.partial.json").unlink(missing_ok=True)
        (cell_dir / "cost.json").write_text(json.dumps(
            {**usage, "agent": manifest.name,
             "pricing_source": f"external:{usage.get('basis')}"}, indent=2))
        if interrupted:
            # The cell is on disk now; let the interrupt do its job.
            print(f"  interrupted: cell persisted to {cell_dir}", flush=True)
            raise KeyboardInterrupt
        return score
    finally:
        if sandbox is not None:
            sandbox.stop()
        shutil.rmtree(root, ignore_errors=True)


if __name__ == "__main__":
    import sys
    sys.exit("the external arm has no standalone CLI.\n"
             "use:  fb-bench run <bugs> --agent path/to/agent.yaml")
