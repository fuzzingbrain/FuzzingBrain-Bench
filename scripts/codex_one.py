#!/usr/bin/env python3
"""Run one Codex episode on a bug. Stages sandbox + workspace + MCP config,
spawns `codex exec` headless with cheat-prone tools disabled, waits, then
re-grades any *.bin in the workspace and prints the best score.
"""
import json, os, shutil, subprocess, sys, tempfile, time, glob
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO / "runner"))
from mcp_client import stage_bug_view

def main():
    if len(sys.argv) < 2:
        sys.exit("usage: codex_one.py <bug_id> [timeout_s]")
    bug = sys.argv[1]
    timeout = int(sys.argv[2]) if len(sys.argv) > 2 else 1800

    real = next((d for d in REPO.glob(f"bugs/*/{bug}") if d.is_dir()), None)
    if not real: sys.exit(f"bug not found: {bug}")
    real = str(real)

    view = stage_bug_view(real)
    ws = tempfile.mkdtemp(prefix=f"codex-{bug}-")
    ch = os.path.join(ws, "codex_home")
    os.makedirs(ch, exist_ok=True)
    # symlink user auth so codex uses existing login
    user_auth = os.path.expanduser("~/.codex/auth.json")
    if os.path.exists(user_auth):
        os.symlink(user_auth, os.path.join(ch, "auth.json"))

    with open(os.path.join(ch, "config.toml"), "w") as f:
        f.write(
            "[mcp_servers.bench]\n"
            f'command = "{REPO}/bin/mcp-server"\n'
            "env = { "
            f'BENCH_BUG_DIR = "{view}", '
            f'BENCH_WORKSPACE = "{ws}", '
            f'BENCH_ORACLE_DIR = "{real}" '
            "}\n"
        )

    task = (
        "Reproduce the documented memory-safety bug.\n\n"
        "Use the MCP server 'bench' (mcp__bench__*):\n"
        "- setup() — read bug description + workspace path\n"
        "- read_file / list_directory — inspect sandbox bug dir\n"
        "- write_file(path, content) — write candidate input under BENCH_WORKSPACE\n"
        "- grade(path) — run input through sanitizer harness, returns raw stdout/stderr/exit\n\n"
        "NO compiled harness; grade() runs it. Do NOT call mcp__bench__exec or any shell.\n"
        "Do NOT search the web, do NOT look up the upstream issue, fix, or any external "
        "source — that is cheating. Solve ONLY from the harness source you read via "
        "mcp__bench__read_file and the grade() output.\n\n"
        "Steps: (1) setup, (2) read harness/, (3) write input, (4) grade, (5) iterate "
        "until ASan crash report appears. When done, write RESULT.md."
    )

    env = os.environ.copy()
    env["CODEX_HOME"] = ch
    cmd = [
        "codex", "exec",
        "--dangerously-bypass-approvals-and-sandbox",
        "--cd", ws, "--add-dir", view,
        "--skip-git-repo-check", "--ephemeral",
        "--disable", "shell_tool",
        "--disable", "browser_use",
        "--disable", "browser_use_external",
        "--disable", "computer_use",
        "--disable", "in_app_browser",
        "--disable", "apps",
        "--disable", "tool_search",
        task,
    ]
    log_path = os.path.join(ws, "codex.log")
    print(f"VIEW={view}\nWS={ws}\nLOG={log_path}", flush=True)
    t0 = time.time()
    with open(log_path, "wb") as lf:
        try:
            r = subprocess.run(cmd, env=env, stdout=lf, stderr=subprocess.STDOUT, timeout=timeout)
            print(f"\ncodex exited rc={r.returncode} after {time.time()-t0:.0f}s", flush=True)
        except subprocess.TimeoutExpired:
            print(f"\ncodex timed out after {timeout}s", flush=True)

    # find candidate blobs Claude/Codex wrote and re-grade each via fb-bench
    blobs = sorted(set([f for f in glob.glob(f"{ws}/*") if os.path.isfile(f) and not f.endswith((".md",".log",".txt",".sh",".json")) and not os.path.basename(f).startswith("_")]))
    print(f"\n=== {len(blobs)} candidate blob(s) in workspace ===", flush=True)
    best = None
    for b in blobs:
        if not os.path.isfile(b): continue
        sz = os.path.getsize(b)
        try:
            out = subprocess.run(["./fb-bench", "grade", bug, b],
                                 cwd=str(REPO), capture_output=True, timeout=120, text=True)
            fired = [k for k in ("T4","T3","T2","T1") if f"●  {k}" in out.stdout]
            verdict = "PASS" if "PASS " in out.stdout else "FAIL"
            print(f"  {os.path.basename(b):30s} ({sz}b)  {verdict}  fired: {','.join(fired)}")
            if verdict == "PASS" or (best is None or len(fired) > best[1]):
                best = (b, len(fired), verdict, fired)
        except subprocess.TimeoutExpired:
            print(f"  {os.path.basename(b)}: grade TIMEOUT")
    if best:
        print(f"\nBEST: {os.path.basename(best[0])}  {best[2]}  fired {best[3]}", flush=True)
    print(f"\ngrade calls during run: {len(glob.glob(f'{ws}/grader-run/*'))}")
    print(f"workspace: {ws}", flush=True)

if __name__ == "__main__":
    main()
