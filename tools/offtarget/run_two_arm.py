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

def run_cell(bug, model, seed, max_turns, arm, oracle):
    out_dir = OUT / arm / bug / model / f"seed-{seed}"
    sj = out_dir / "score.json"
    if sj.is_file():
        return json.loads(sj.read_text())
    out_dir.mkdir(parents=True, exist_ok=True)
    # NO --force-full: the agent may stop when it believes it succeeded. That is
    # exactly where off-target interference bites (a non-preset crash causing a
    # premature/false-success stop or wasted turns), so it must be measurable.
    cmd = RUNNER + ["--bug", bug, "--model", model, "--max-turns", str(max_turns),
                    "--out-dir", str(out_dir), "--preserve-pocs"]
    if oracle: cmd += ["--oracle-dir", str(oracle)]
    env = dict(os.environ); env["PYTHONHASHSEED"] = str(seed); env["FBBENCH_SEED"] = str(seed)
    p = subprocess.run(cmd, cwd=str(ROOT), env=env, capture_output=True, text=True, timeout=max_turns*60)
    if sj.is_file(): return json.loads(sj.read_text())
    return {"error": "no score.json", "stderr": p.stderr[-500:]}

def solved(score, kb_keys):
    caps = score.get("capabilities", {})
    return bool(kb_keys) and all(caps.get(k) == "fired" for k in kb_keys)

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--models", default="claude-haiku-4-5")
    ap.add_argument("--seeds", default="0")
    ap.add_argument("--max-turns", type=int, default=150)
    ap.add_argument("--bugs", default=None, help="comma list; default = all staged Arm-B bugs")
    a = ap.parse_args()
    all_staged = staged_bugs()
    if a.bugs:
        want = set(a.bugs.split(","))
        cells = [(b, p) for (b, p) in all_staged if b in want]
    else:
        cells = all_staged
    models = a.models.split(","); seeds = [int(x) for x in a.seeds.split(",")]
    print(f"two-arm eval: {len(cells)} bugs x {len(models)} models x {len(seeds)} seeds")
    rows = []
    for bug, proj in cells:
        from fbbench.grading.bench_yaml import capability_set
        kb = capability_set(ROOT / "bugs" / proj / bug)
        for model in models:
            for seed in seeds:
                a_score = run_cell(bug, model, seed, a.max_turns, "armA", None)
                b_score = run_cell(bug, model, seed, a.max_turns, "armB", ARMB / proj / bug)
                sa, sb = solved(a_score, kb), solved(b_score, kb)
                ta, tb = a_score.get("turns_used"), b_score.get("turns_used")
                rows.append({"bug": bug, "model": model, "seed": seed,
                             "solved_A": sa, "solved_B": sb,
                             "turns_A": ta, "turns_B": tb,
                             "tier_A": a_score.get("tier_score"), "tier_B": b_score.get("tier_score")})
                print(f"  {bug:40s} {model:18s} s{seed}  A:solved={int(sa)} t={ta}  "
                      f"B:solved={int(sb)} t={tb}", flush=True)
    OUT.mkdir(parents=True, exist_ok=True)
    json.dump(rows, open(OUT / "two_arm_results.json", "w"), indent=2)
    # summary
    na = sum(r["solved_A"] for r in rows); nb = sum(r["solved_B"] for r in rows)
    print(f"\n=== SUMMARY ({len(rows)} cells) ===")
    print(f"  solved  ArmA(interference)={na}   ArmB(clean)={nb}   delta(B-A)={nb-na}")
    flips = [r for r in rows if r["solved_B"] and not r["solved_A"]]
    print(f"  bugs solved ONLY without interference (B not A): {len(flips)}")
    for r in flips: print(f"    {r['bug']} {r['model']} seed{r['seed']}")

if __name__ == "__main__":
    main()
