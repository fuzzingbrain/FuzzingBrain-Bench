#!/usr/bin/env python3
"""Step 7 — two-arm off-target ablation eval.

For each rebuilt bug (one that has a staged Arm-B oracle under bugs-armB/), run the
SAME agent (model + seed + max-turns) twice:
  Arm A (with interference)    : normal oracle  bugs/<proj>/<bug>      (old V1)
  Arm B (interference-free)    : --oracle-dir   bugs-armB/<proj>/<bug> (new V1)
Parse each score.json and report the per-bug delta (solved, turns, tier_score).
delta = Arm A − Arm B = the effect of other-bug interference on finding the preset.

Only rebuilt bugs are run (the other ~56 bugs are byte-identical across arms → null,
no agent budget spent). Resumable: skips a cell whose score.json already exists.

Usage:
  run_two_arm.py --models claude-haiku-4-5 --seeds 0,1 --max-turns 150 [--bugs a,b]
"""
from __future__ import annotations
import argparse, json, os, subprocess, sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
ARMB = ROOT / "bugs-armB"
OUT = ROOT / "runs" / "offtarget-eval"
RUNNER = [sys.executable, "-m", "fbbench.runner"]

def staged_bugs():
    bugs = []
    if not ARMB.exists(): return bugs
    for proj in sorted(ARMB.iterdir()):
        if proj.is_dir():
            for b in sorted(proj.iterdir()):
                if (b / "binaries" / "release-asan" / "harness").exists():
                    bugs.append((b.name, proj.name))
    return bugs

DIFF_EXP = ROOT / "tools" / "diffscan_experiment.py"

def mode_tag(mode, diff_level):
    return f"diff-{diff_level}" if mode == "diff" else mode

def run_cell(bug, model, seed, max_turns, arm, oracle, mode, diff_level=0):
    out_dir = OUT / mode_tag(mode, diff_level) / arm / bug / model / f"seed-{seed}"
    sj = out_dir / "score.json"
    if sj.is_file():
        return json.loads(sj.read_text())
    out_dir.mkdir(parents=True, exist_ok=True)
    # NO --force-full: the agent may stop when it believes it succeeded. That is
    # exactly where off-target interference bites (a non-preset crash causing a
    # premature/false-success stop or wasted turns), so it must be measurable.
    if mode == "diff":
        cmd = [sys.executable, str(DIFF_EXP), "--bug", bug, "--model", model,
               "--diff-level", str(diff_level), "--max-turns", str(max_turns), "--out-dir", str(out_dir)]
    else:  # normal | full
        cmd = RUNNER + ["--bug", bug, "--model", model, "--max-turns", str(max_turns),
                        "--out-dir", str(out_dir), "--preserve-pocs"]
        if mode == "full":
            cmd += ["--full-scan"]
    if oracle: cmd += ["--oracle-dir", str(oracle)]
    env = dict(os.environ); env["PYTHONHASHSEED"] = str(seed); env["FBBENCH_SEED"] = str(seed)
    try:
        p = subprocess.run(cmd, cwd=str(ROOT), env=env, capture_output=True, text=True, timeout=max_turns*90)
    except subprocess.TimeoutExpired:
        return {"error": "timeout"}
    if sj.is_file(): return json.loads(sj.read_text())
    return {"error": "no score.json", "stderr": (p.stderr or "")[-300:]}

def solved(score, kb_keys):
    caps = (score or {}).get("capabilities", {})
    return bool(kb_keys) and all(caps.get(k) == "fired" for k in kb_keys)

# report-aligned per-mode turn budgets (full-v1 REPORT.md): normal/diff 50, full 100.
MODE_TURNS = {"normal": 50, "full": 100, "diff": 50}

def main():
    from concurrent.futures import ThreadPoolExecutor, as_completed
    from fbbench.grading.bench_yaml import capability_set
    ap = argparse.ArgumentParser()
    ap.add_argument("--models", default="claude-haiku-4-5,gpt-5.5")
    ap.add_argument("--seeds", default="0")
    ap.add_argument("--bugs", default=None, help="comma list; default = all staged Arm-B bugs")
    ap.add_argument("--modes", default="normal,full,diff-0,diff-1,diff-2,diff-3",
                    help="comma list of normal|full|diff-N")
    ap.add_argument("--concurrency", type=int, default=6)
    a = ap.parse_args()
    all_staged = staged_bugs()
    cells_bugs = ([(b, p) for (b, p) in all_staged if b in set(a.bugs.split(","))]
                  if a.bugs else all_staged)
    models = a.models.split(","); seeds = [int(x) for x in a.seeds.split(",")]
    modespec = a.modes.split(",")
    kb_of = {bug: capability_set(ROOT / "bugs" / proj / bug) for bug, proj in cells_bugs}
    # build the full task list: (modespec, bug, proj, model, seed, arm)
    tasks = []
    for ms in modespec:
        mode = "diff" if ms.startswith("diff") else ms
        dl = int(ms.split("-")[1]) if ms.startswith("diff") else 0
        mt = MODE_TURNS[mode]
        for bug, proj in cells_bugs:
            for model in models:
                for seed in seeds:
                    for arm, oracle in (("armA", None), ("armB", ARMB / proj / bug)):
                        tasks.append((ms, mode, dl, mt, bug, proj, model, seed, arm, oracle))
    print(f"aligned matrix: {len(modespec)} modes x {len(models)} models x {len(cells_bugs)} bugs "
          f"x 2 arms x {len(seeds)} seeds = {len(tasks)} episodes (concurrency {a.concurrency})", flush=True)
    def work(t):
        ms, mode, dl, mt, bug, proj, model, seed, arm, oracle = t
        sc = run_cell(bug, model, seed, mt, arm, oracle, mode, dl)
        return (ms, bug, model, seed, arm, sc)
    done = 0
    with ThreadPoolExecutor(max_workers=a.concurrency) as ex:
        futs = {ex.submit(work, t): t for t in tasks}
        for f in as_completed(futs):
            ms, bug, model, seed, arm, sc = f.result()
            done += 1
            s = solved(sc, kb_of[bug]); tu = (sc or {}).get("turns_used"); err = (sc or {}).get("error", "")
            print(f"  [{done}/{len(tasks)}] {ms:7s} {arm} {bug:34s} {model:16s} "
                  f"solved={int(s)} t={tu} {err}", flush=True)
    # aggregate per (mode, model): A vs B
    print("\n=== SUMMARY (solved A=interference vs B=clean) ===")
    agg = {}
    for ms in modespec:
        mode = "diff" if ms.startswith("diff") else ms
        dl = int(ms.split("-")[1]) if ms.startswith("diff") else 0
        for model in models:
            na=nb=n=0
            for bug, proj in cells_bugs:
                for seed in seeds:
                    A=run_cell(bug,model,seed,MODE_TURNS[mode],"armA",None,mode,dl)
                    B=run_cell(bug,model,seed,MODE_TURNS[mode],"armB",ARMB/proj/bug,mode,dl)
                    if (A or {}).get("error") or (B or {}).get("error"): continue
                    n+=1; na+=solved(A,kb_of[bug]); nb+=solved(B,kb_of[bug])
            agg[(ms,model)]={"n":n,"A":na,"B":nb}
            print(f"  {ms:7s} {model:16s}  A={na}/{n}  B={nb}/{n}  delta(B-A)={nb-na}")
    OUT.mkdir(parents=True, exist_ok=True)
    json.dump({f"{k[0]}|{k[1]}":v for k,v in agg.items()},
              open(OUT/"aligned_matrix_summary.json","w"), indent=2)

if __name__ == "__main__":
    main()
