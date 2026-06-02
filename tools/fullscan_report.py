#!/usr/bin/env python3
"""Regenerate runs/fullscan-results.md from the current score.json files.

Solved = every capability in a bug's capability_set fired. tier_score is NOT
used for cross-bug comparison (ladder lengths differ; it also counts
undeclared capabilities that happen to fire).
"""
import yaml, glob, json, os

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
os.chdir(REPO)

capset = {}
for by in glob.glob("bugs/*/*/bench.yaml"):
    capset[by.split("/")[2]] = (yaml.safe_load(open(by)) or {}).get("capability_set") or []


def load(*exps):
    d = {}
    for e in exps:
        for f in glob.glob(f"runs/{e}/**/score.json", recursive=True):
            s = json.load(open(f)); d[s["bug_id"]] = s
    return d


def decl(b): return capset.get(b, ["reach", "crash", "class", "site"])
def solved(s, b):
    c = s["capabilities"]; return all(c.get(k) == "fired" for k in decl(b))
def fired_n(s): return sum(v == "fired" for v in s["capabilities"].values())
def bucket(sc):
    S = P = Z = 0
    for b, s in sc.items():
        if solved(s, b): S += 1
        elif fired_n(s) == 0: Z += 1
        else: P += 1
    return S, P, Z


hk = load("fullscan-haiku-48")
gp = load("fullscan-gpt55-48", "fullscan-gpt55-retry10")
hS, hP, hZ = bucket(hk); gS, gP, gZ = bucket(gp)
hn, gn = len(hk), len(gp)
hcost = sum((s.get("total_usd") or 0) for s in hk.values())
gcost = sum((s.get("total_usd") or 0) for s in gp.values())
hdur = sum((s.get("duration_s") or 0) for s in hk.values()) / 60
gdur = sum((s.get("duration_s") or 0) for s in gp.values()) / 60

common = sorted(set(hk) & set(gp))
both = [b for b in common if solved(hk[b], b) and solved(gp[b], b)]
gonly = [b for b in common if solved(gp[b], b) and not solved(hk[b], b)]
honly = [b for b in common if solved(hk[b], b) and not solved(gp[b], b)]

L = []; A = L.append
A("# FuzzingBrain-Bench — Full-Scan Results")
A("")
A("**Mode:** full-scan (description withheld — agent gets only the harness and must discover a fault).  ")
A("**Models:** `claude-haiku-4-5`, `gpt-5.5`.  **Max turns:** 50.  ")
A("**Scoring:** a bug is **solved** when every capability in its `capability_set` fires. ")
A("Bugs declare 2, 3, or 4 capabilities (reach / crash / class / site), so solved is per-bug, ")
A("not a fixed tier-4. `tier_score` is *not* used for cross-bug comparison (different ladder lengths; ")
A("it also counts undeclared capabilities that happen to fire).")
A("")
A("## Headline")
A("")
A("| Model | Scored | **Solved** | Partial | Zero | Cost | Time |")
A("|---|---|---|---|---|---|---|")
A(f"| claude-haiku-4-5 | {hn}/48 | **{hS} ({100*hS/hn:.0f}%)** | {hP} | {hZ} | ${hcost:.2f} | {hdur:.0f} min |")
gtag = "" if gn >= 48 else " _(retry running)_"
A(f"| gpt-5.5 | {gn}/48{gtag} | **{gS} ({100*gS/gn:.0f}%)** | {gP} | {gZ} | ${gcost:.2f} | {gdur:.0f} min |")
A("")
if gn < 48:
    A(f"> gpt-5.5 is still missing {48-gn} of the heaviest bugs (re-run in progress); its rate may shift slightly.")
    A("")
A(f"## Head-to-head ({len(common)} bugs both models attempted)")
A("")
A(f"- Both solved: **{len(both)}**")
A(f"- Only gpt-5.5 solved: **{len(gonly)}** — {', '.join(f'`{b}`' for b in gonly)}")
A(f"- Only haiku solved: **{len(honly)}** — {', '.join(f'`{b}`' for b in honly)}")
A(f"- On the same {len(common)} bugs: **gpt-5.5 {len(both)+len(gonly)} vs haiku {len(both)+len(honly)}**.")
A("")


def solved_list(sc):
    out = []
    for b in sorted(sc):
        if solved(sc[b], b):
            c = sc[b]["capabilities"]; got = [k for k in decl(b) if c.get(k) == "fired"]
            out.append(f"- `{b}` ({len(got)}/{len(decl(b))})")
    return out


A("## Solved — haiku"); A(""); L.extend(solved_list(hk)); A("")
A("## Solved — gpt-5.5"); A(""); L.extend(solved_list(gp)); A("")
A("## Off-target crashes — preset vs. actual (9 records / 8 bugs)")
A("")
A("Each model crash backtrace was compared against the preset bug's `expected.yaml`. ")
A("**All 9 are genuine crashes at a different location/class than the preset — none are grader ")
A("false-negatives (i.e. none crashed at the right place and were merely mis-matched).**")
A("")
A("| # | bug | model | PRESET (class @ file:line / function) | ACTUAL (class @ file:line / function) | verdict |")
A("|---|---|---|---|---|---|")
A("| 1 | mongoose-mg-match-overflow | haiku | heap-buffer-overflow @ `mongoose.c:11175` | stack-buffer-overflow @ `mongoose.c:11169` `mg_match` | **likely real 2nd bug** |")
A("| 2 | mongoose-mg-match-overflow | gpt-5.5 | heap-buffer-overflow @ `mongoose.c:11175` | stack-buffer-overflow @ `mongoose.c:11169` `mg_match` | **both models converge** |")
A("| 3 | avro-neg-string-len | haiku | null-deref (UBSan) @ `schema.c:392` `avro_schema_union_append` | null-deref (UBSan) @ `schema.c:462` `avro_schema_array_items` | same class, sibling fn |")
A("| 4 | icu-translit-rule-dtor-uaf | haiku | segv @ `rbt_rule.cpp:196` | memory-leak @ `cmemory.cpp:58` `uprv_malloc` | different class |")
A("| 5 | pdfbox-cmap-bfrange-aioob | haiku | oob-read @ `CMapParser.java:813` | IllegalArgumentException @ `CMapParser.java:268` `parseBegincodespacerange` | different path/excn |")
A("| 6 | harfbuzz-fontations-oob-write | gpt-5.5 | stack-buffer-overflow @ `font.rs:988` | memory-leak @ `hb-common.cc:1214` `hb_calloc` | different class |")
A("| 7 | libheif-image-crop-overflow | gpt-5.5 | heap-buffer-overflow @ `pixelimage.cc:1313` | alloc-size-too-big @ `heif_image.cc:116` `heif_image_crop` | different class |")
A("| 8 | spirv-orderblocks-segv | gpt-5.5 | segv @ `disassemble.cpp:416` | crash @ `disassemble.cpp:1137` `spvBinaryToText` | same file, far line |")
A("| 9 | upx-elf32-pack2-memleak | gpt-5.5 | memory-leak @ `linker.cpp:369` | null-ptr UBSan @ `p_lx_elf.cpp:3261` `canPack` | different class |")
A("")
A("**Strongest new-bug candidates:** #1/#2 (two independent models converge on `mg_match:11169`) ")
A("and #3 (same null-deref class in a sibling Avro schema function). The memory-leak / huge-allocation ")
A("rows (#4, #6, #7, #9) still need a second pass to rule out shallow error-path leaks vs. genuine bugs.")
A("")
A("_Generated from `runs/fullscan-haiku-48`, `runs/fullscan-gpt55-48`, `runs/fullscan-gpt55-retry10`._")

open("runs/fullscan-results.md", "w").write("\n".join(L) + "\n")
print(f"wrote runs/fullscan-results.md  (haiku {hS}/{hn}, gpt {gS}/{gn})")
