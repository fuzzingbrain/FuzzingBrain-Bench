"""The challenge-container sandbox: no network, and no libFuzzer fuzzing loop.

The preload is exercised on the host against a stand-in libFuzzer binary -- a
copy of /bin/true carrying libFuzzer's marker string -- so this needs neither
docker nor a compiler. The live checks (a real harness, gdb, the grader) are in
the episode images and were run by hand; see fbbench/sandbox.py.
"""
import inspect
import json
import os
import shutil
import subprocess

import pytest

from fbbench import sandbox
from fbbench.sandbox import NOFUZZ_REFUSED, NOFUZZ_SO, sandbox_args

MARKER = b"Number of individual test runs"


@pytest.fixture
def fake_fuzzer(tmp_path):
    """An executable that libFuzzer detection must recognise, and that exits 0."""
    true = shutil.which("true")
    exe = tmp_path / "harness"
    exe.write_bytes(open(true, "rb").read() + b"\0" + MARKER + b"\0")
    exe.chmod(0o755)
    return exe


def _run(exe, *args, cwd=None):
    env = dict(os.environ, LD_PRELOAD=NOFUZZ_SO)
    return subprocess.run([str(exe), *args], env=env, cwd=cwd,
                          capture_output=True, text=True, timeout=30)


@pytest.mark.parametrize("args", [
    (),                                  # no input: libFuzzer's default is to fuzz
    ("-max_len=64",),                    # flags alone are still no input
    ("-minimize_crash=1", "FILE"),       # mutates the crash it is given
    ("-cleanse_crash=1", "FILE"),
    ("-fork=2", "FILE"),
    ("-jobs=4", "FILE"),
    ("-workers=2", "FILE"),
    ("DIR",),                            # a corpus directory is fuzzed
    ("-runs=5", "DIR"),
])
def test_a_fuzzing_run_is_refused(fake_fuzzer, tmp_path, args):
    (tmp_path / "in").write_bytes(b"x")
    (tmp_path / "corpus").mkdir()
    argv = [{"FILE": str(tmp_path / "in"), "DIR": str(tmp_path / "corpus")}.get(a, a)
            for a in args]
    r = _run(fake_fuzzer, *argv)
    assert r.returncode == 1
    assert NOFUZZ_REFUSED in r.stderr
    # A refusal that does not say what to do instead wastes the turn.
    assert "input files you" in r.stderr and "-runs=0" in r.stderr


@pytest.mark.parametrize("args", [
    ("FILE",),                           # the ordinary way to run one input
    ("FILE", "FILE"),
    ("-runs=3", "FILE"),                 # repeats an input; generates nothing
    ("-runs=0", "-print_coverage=1", "DIR"),   # the coverage recipe in the prompt
    ("-help=1",),
    ("/no/such/path",),                  # libFuzzer reports that one itself
])
def test_running_given_inputs_is_allowed(fake_fuzzer, tmp_path, args):
    (tmp_path / "in").write_bytes(b"x")
    (tmp_path / "corpus").mkdir()
    argv = [{"FILE": str(tmp_path / "in"), "DIR": str(tmp_path / "corpus")}.get(a, a)
            for a in args]
    r = _run(fake_fuzzer, *argv)
    assert r.returncode == 0, r.stderr
    assert NOFUZZ_REFUSED not in r.stderr


def test_only_libfuzzer_binaries_are_refused(tmp_path):
    """Every process in the container carries the preload; `ls` with no
    arguments must still just list."""
    r = _run(shutil.which("ls"), cwd=tmp_path)
    assert r.returncode == 0 and NOFUZZ_REFUSED not in r.stderr


def test_a_copied_binary_is_still_recognised(fake_fuzzer, tmp_path):
    """Detection is by what the binary is, not where it lives."""
    copy = tmp_path / "elsewhere"
    shutil.copy(fake_fuzzer, copy)
    assert NOFUZZ_REFUSED in _run(copy).stderr


def test_the_preload_runs_on_old_images():
    """Built on a new host, but loaded by each image's own glibc. A symbol
    versioned past 2.2.5 would make every process in the container print a
    loader error and run unguarded."""
    objdump = shutil.which("objdump")
    if objdump is None:
        pytest.skip("objdump not installed")
    out = subprocess.run([objdump, "-T", NOFUZZ_SO], capture_output=True, text=True).stdout
    versions = {w.strip("()") for w in out.split() if w.startswith("(GLIBC_")}
    assert versions <= {"GLIBC_2.2.5"}, versions


# ------------------------------------------------------- every launch site
def test_every_challenge_container_gets_the_sandbox():
    """One definition, used wherever a challenge container is started. A launch
    site without it is an arm that can fuzz, or a grader at the host's mercy."""
    from fbbench.runner import mcp_client
    from fbbench.sweep import codex, mcp_episode
    assert "sandbox_args()" in inspect.getsource(mcp_episode._start_episode_server)
    assert "sandbox_args()" in inspect.getsource(mcp_client.MCPClient.__init__)
    assert "sandbox_args()" in inspect.getsource(codex.stage_codex_env)
    assert "{sandbox}" in codex._CODEX_CONFIG


def test_the_sandbox_flags():
    args = sandbox_args()
    assert args[args.index("--network") + 1] == "none"
    assert f"LD_PRELOAD={sandbox.NOFUZZ_IN_CONTAINER}" in args
    assert f"{NOFUZZ_SO}:{sandbox.NOFUZZ_IN_CONTAINER}:ro" in args


def test_a_missing_guard_is_an_error_not_an_open_door(monkeypatch, tmp_path):
    monkeypatch.setattr(sandbox, "NOFUZZ_SO", str(tmp_path / "gone.so"))
    with pytest.raises(FileNotFoundError):
        sandbox.sandbox_args()


def test_the_codex_config_is_still_valid_toml(tmp_path, monkeypatch):
    tomllib = pytest.importorskip("tomllib")
    from fbbench.sweep import codex
    text = codex._CODEX_CONFIG.format(
        image="img", ws="/w", model="m", login="api",
        sandbox=", ".join(json.dumps(a) for a in sandbox_args()))
    args = tomllib.loads(text)["mcp_servers"]["harness"]["args"]
    assert args[args.index("--network") + 1] == "none"
    assert args[-2:] == ["img", "mcp-server"]


# ------------------------------------------------------------ the record
def test_a_refusal_inside_the_container_is_recorded(tmp_path):
    from fbbench.sweep.mcp_episode import CandidateLog
    log = CandidateLog(tmp_path / "cell", str(tmp_path))
    req = {"jsonrpc": "2.0", "id": 7, "method": "tools/call",
           "params": {"name": "exec", "arguments": {"cmd": "/opt/h"}}}
    log.saw_request((json.dumps(req) + "\n").encode())
    body = {"stdout": "", "stderr": NOFUZZ_REFUSED + ", and\n...", "exit_code": 0}
    resp = {"jsonrpc": "2.0", "id": 7, "result": {"structuredContent": body}}
    log.saw_response((json.dumps(resp) + "\n").encode())
    assert [b["cmd"] for b in log.blocked] == ["/opt/h"]
    assert (tmp_path / "cell" / "blocked.jsonl").is_file()


def test_an_ordinary_exec_is_not_recorded(tmp_path):
    from fbbench.sweep.mcp_episode import CandidateLog
    log = CandidateLog(tmp_path / "cell", str(tmp_path))
    req = {"jsonrpc": "2.0", "id": 8, "method": "tools/call",
           "params": {"name": "mcp__bench__exec", "arguments": {"cmd": "ls"}}}
    log.saw_request((json.dumps(req) + "\n").encode())
    resp = {"jsonrpc": "2.0", "id": 8,
            "result": {"structuredContent": {"stdout": "a\n", "exit_code": 0}}}
    log.saw_response((json.dumps(resp) + "\n").encode())
    assert log.blocked == [] and log.entries == []
