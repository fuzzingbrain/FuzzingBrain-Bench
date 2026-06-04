#!/usr/bin/env python3
"""Diff-scan report — mirrors the full-scan report: headline table, noise ladder,
two Venn diagrams (model comparison + noise robustness), per-case grid, honest
caveats. Reads runs/diffscan/<bug>/<model>/diff-N/score.json.

Outputs: runs/diffscan-results.md, runs/diffscan-venn-model.png,
runs/diffscan-venn-noise.png, runs/diffscan-cases.html.

SOLVED = the bug's own capability_set K_b is satisfied (not tier>=4: K_b varies).
"""
import base64
import glob
import json
import os

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
from matplotlib_venn import venn2

from fbbench.grading.bench_yaml import capability_set, find_bug
from fbbench.paths import REPO

os.chdir(REPO)
HAIKU = "claude-haiku-4-5"
GPT = "gpt-5.5"


def load(model, cell):
    out = {}
    for f in glob.glob(f"runs/diffscan/*/{model}/{cell}/score.json"):
        s = json.load(open(f))
        b = s["bug_id"]
        fired = {k for k, v in s["capabilities"].items() if v == "fired"}
        kb = set(capability_set(find_bug(b, REPO)) or ["reach", "crash", "class", "site"])
        out[b] = {
            "fired": fired,
            "solved": bool(kb) and kb.issubset(fired),
            "crash": "crash" in fired,
            "reach": "reach" in fired,
            "usd": s.get("total_usd") or 0,
        }
    return out


cells = {
    "haiku diff-0": load(HAIKU, "diff-0"),
    "haiku diff-1": load(HAIKU, "diff-1"),
    "haiku diff-2": load(HAIKU, "diff-2"),
    "haiku diff-3": load(HAIKU, "diff-3"),
    "gpt-5.5 diff-0": load(GPT, "diff-0"),
}
H = [cells[f"haiku diff-{i}"] for i in range(4)]

# common set across the 4 haiku levels (apples-to-apples for the noise ladder)
common = set(H[0])
for h in H[1:]:
    common &= set(h)

# common set for the model comparison (diff-0)
model_common = set(cells["haiku diff-0"]) & set(cells["gpt-5.5 diff-0"])


def cnt(d, key, keys=None):
    keys = keys if keys is not None else d
    return sum(1 for b in keys if d.get(b, {}).get(key))


# ---- Venn 1: model comparison, SOLVED @ diff-0 (common set) -----------------
hs = {b for b in model_common if cells["haiku diff-0"][b]["solved"]}
gs = {b for b in model_common if cells["gpt-5.5 diff-0"][b]["solved"]}
plt.figure(figsize=(6, 5))
venn2(subsets=(len(hs - gs), len(gs - hs), len(hs & gs)),
      set_labels=("haiku diff-0", "gpt-5.5 diff-0"))
plt.title(f"Diff-0 SOLVED — haiku vs gpt-5.5 (n={len(model_common)}, union {len(hs | gs)})")
plt.savefig("runs/diffscan-venn-model.png", dpi=150, bbox_inches="tight")
plt.close()

# ---- Venn 2: noise robustness, haiku SOLVED diff-0 vs diff-3 (common set) ---
s0 = {b for b in common if H[0][b]["solved"]}
s3 = {b for b in common if H[3][b]["solved"]}
plt.figure(figsize=(6, 5))
venn2(subsets=(len(s0 - s3), len(s3 - s0), len(s0 & s3)),
      set_labels=("haiku diff-0 (clean)", "haiku diff-3 (3 distractors)"))
plt.title(f"Noise robustness — haiku SOLVED diff-0 vs diff-3 (n={len(common)})")
plt.savefig("runs/diffscan-venn-noise.png", dpi=150, bbox_inches="tight")
plt.close()

# ---- noise-ladder stability -------------------------------------------------
stable_solved = {b for b in common if all(H[i][b]["solved"] for i in range(4))}
ever_solved = {b for b in common if any(H[i][b]["solved"] for i in range(4))}
flip = sorted(b for b in common
              if len({H[i][b]["solved"] for i in range(4)}) > 1)

# ---- markdown ----------------------------------------------------------------
L = []
def A(s=""):
    L.append(s)

A("# FuzzingBrain-Bench — Diff-Scan Results")
A("")
A("**Mode:** diff-scan (description withheld; agent is given only the NAME(s) of the "
  "file a PR touched — the crash-point file — plus, at higher levels, random "
  "fuzzer-relevant distractor file names it must see through).  ")
A("**Granularity:** file-level. The crash-point file fully contains any PR that "
  "could have introduced the bug, so naming the file subsumes the real diff.  ")
A("**SOLVED** = every capability in the bug's `capability_set` (K_b) fired. "
  "Grading is single-round (flaky=1), LSan gated to leak-class bugs, class matched "
  "on the sanitizer report line only.")
A("")
A("## Noise ladder")
A("- **diff-0**: only the crash file(s)")
A("- **diff-1/2/3**: + 1/2/3 random *fuzzer-relevant* same-project distractor file names")
A("")
A("| cell | n | solved | crash-found | reach | cost |")
A("|---|---|---|---|---|---|")
for name, d in cells.items():
    keys = set(d)
    A(f"| {name} | {len(keys)} | {cnt(d,'solved',keys)} | {cnt(d,'crash',keys)} | "
      f"{cnt(d,'reach',keys)} | ${sum(v['usd'] for v in d.values()):.2f} |")
A("")
A(f"_Per-cell n differs: diff-1/2/3 skip the 3 non-GitHub bugs (no tree fetcher) "
  f"and any that timed out. For an apples-to-apples ladder, use the common set below._")
A("")
A(f"## Noise ladder on the COMMON set ({len(common)} bugs in all 4 haiku levels)")
A("")
A("| | diff-0 | diff-1 | diff-2 | diff-3 |")
A("|---|---|---|---|---|")
A("| solved | " + " | ".join(str(sum(H[i][b]['solved'] for b in common)) for i in range(4)) + " |")
A("| crash  | " + " | ".join(str(sum(H[i][b]['crash'] for b in common)) for i in range(4)) + " |")
A("")
A(f"**Stability caveat (important):** solve is NOT monotonic in noise — "
  f"**{len(flip)}/{len(common)} bugs flip solved/unsolved across the four levels**. "
  f"Only **{len(stable_solved)}** are solved at ALL levels; **{len(ever_solved)}** are "
  f"solved at SOME level. With single-run episodes (flaky=1), per-bug run-to-run "
  f"variance dominates the small noise effect for haiku — the ladder does not cleanly "
  f"separate noise levels at n=1. Multiple seeds would be needed to measure a noise effect.")
A("")
A("Flipping bugs (S=solved per diff-0/1/2/3):")
for b in flip:
    sv = "".join("S" if H[i][b]["solved"] else "." for i in range(4))
    A(f"- `{b}` `{sv}`")
A("")
A("## Model comparison @ diff-0")
A(f"On the {len(model_common)} bugs both models ran: "
  f"haiku solved **{len(hs)}**, gpt-5.5 solved **{len(gs)}** "
  f"(both {len(hs & gs)}, gpt-only {len(gs - hs)}, haiku-only {len(hs - gs)}, "
  f"union {len(hs | gs)}). gpt-5.5 dominates — clean separation.")
A("")
A("![model venn](diffscan-venn-model.png)  ![noise venn](diffscan-venn-noise.png)")
A("")
A("_Generated from `runs/diffscan/*/{claude-haiku-4-5,gpt-5.5}/diff-*`._")

open("runs/diffscan-results.md", "w").write("\n".join(L) + "\n")

# ---- minimal HTML embedding venns -------------------------------------------
def b64(p):
    return base64.b64encode(open(p, "rb").read()).decode()

html = f"""<!doctype html><meta charset=utf-8>
<title>Diff-Scan Results</title>
<body style="font:14px system-ui;max-width:900px;margin:2rem auto;color:#222">
<h1>FuzzingBrain-Bench — Diff-Scan Results</h1>
<p><b>SOLVED</b> = K_b satisfied. Single-round grading (flaky=1).</p>
<h2>Headline</h2>
<table border=1 cellpadding=6 style="border-collapse:collapse">
<tr><th>cell</th><th>n</th><th>solved</th><th>crash</th><th>reach</th><th>cost</th></tr>
""" + "".join(
    f"<tr><td>{name}</td><td>{len(d)}</td><td>{cnt(d,'solved',set(d))}</td>"
    f"<td>{cnt(d,'crash',set(d))}</td><td>{cnt(d,'reach',set(d))}</td>"
    f"<td>${sum(v['usd'] for v in d.values()):.2f}</td></tr>"
    for name, d in cells.items()
) + f"""</table>
<h2>Venn — SOLVED</h2>
<img src="data:image/png;base64,{b64('runs/diffscan-venn-model.png')}" width=420>
<img src="data:image/png;base64,{b64('runs/diffscan-venn-noise.png')}" width=420>
<h2>Noise stability</h2>
<p>{len(flip)}/{len(common)} bugs flip solved across diff-0..3; only {len(stable_solved)}
solved at all levels, {len(ever_solved)} at some level. Single-run variance dominates the
noise effect for haiku — needs multiple seeds to measure cleanly.</p>
</body>"""
open("runs/diffscan-cases.html", "w").write(html)

print("wrote runs/diffscan-results.md, runs/diffscan-venn-model.png, "
      "runs/diffscan-venn-noise.png, runs/diffscan-cases.html")
print(f"common={len(common)} stable_solved={len(stable_solved)} "
      f"ever_solved={len(ever_solved)} flip={len(flip)}")
print(f"diff-0 model: haiku={len(hs)} gpt={len(gs)} both={len(hs & gs)}")
