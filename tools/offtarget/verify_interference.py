#!/usr/bin/env python3
"""For each catalogued off-target, run its PoC(s) on the MAPPED bundle's existing
release-asan binary (the Arm-A 'with interference' binary) and confirm the crash
is OFF-target (crash fires but bug's preset capability set K_b is NOT satisfied).
Self-validates the off-target->bundle mapping and that the interference is real."""
import os, glob, json, tempfile, shutil, sys
from fbbench.grading.bench_yaml import capability_set, find_bug
from fbbench.paths import REPO
from fbbench.runner.mcp_client import MCPClient, stage_bug_view

OT="/data4/ze/O2_Vulnerability_Management/incoming_report"
server=str(REPO/"bin"/"mcp-server")
inv=json.load(open(REPO/"tools/offtarget/inventory.json"))
out=[]
for e in inv:
    entry=e["entry"]; bundle=e["bundle"]
    pocs=sorted(glob.glob(os.path.join(OT,entry,"poc","*")))
    bug=bundle.split("/")[-1]
    bd=find_bug(bug,REPO)
    rec={"entry":entry,"bundle":bundle,"bucket":e["bucket"],"pocs":len(pocs),"results":[]}
    if bd is None or not pocs:
        rec["error"]="no bundle dir" if bd is None else "no pocs"; out.append(rec); print(f"SKIP {entry}: {rec['error']}"); continue
    kb=set(capability_set(bd))
    ws=tempfile.mkdtemp(); view=stage_bug_view(str(bd),full_scan=False)
    try:
        m=MCPClient(server,bug_dir=view,workspace=ws,oracle_dir=str(bd)); m.initialize(); m.call("setup",{})
        for p in pocs:
            dst=os.path.join(ws,os.path.basename(p)); shutil.copy2(p,dst)
            try: r=m.call("grade",{"path":dst})
            except Exception as ex: rec["results"].append({"poc":os.path.basename(p),"error":str(ex)[:80]}); continue
            caps={k for k,v in r.get("capabilities",{}).items() if v=="fired"}
            act=r.get("evidence",{}).get("actual",{})
            fr=(act.get("frames") or [{}])[0]
            rec["results"].append({
                "poc":os.path.basename(p),
                "crash":"crash" in caps,
                "solved_preset":kb.issubset(caps),
                "fired":sorted(caps),
                "actual_class":act.get("class"),
                "actual_frame":f"{fr.get('func','')} @ {fr.get('file','')}:{fr.get('line','')}",
            })
    finally:
        shutil.rmtree(ws,ignore_errors=True); shutil.rmtree(view,ignore_errors=True)
    # verdict: off-target confirmed if any poc crashes but none solve preset
    anycrash=any(x.get("crash") for x in rec["results"])
    anysolve=any(x.get("solved_preset") for x in rec["results"])
    rec["verdict"]=("offtarget-confirmed" if anycrash and not anysolve else
                    "solves-preset" if anysolve else
                    "no-crash" if rec["results"] else "no-data")
    out.append(rec)
    print(f"{rec['verdict']:20s} {entry[:44]:44s} kb={sorted(kb)}")
    for x in rec["results"]:
        if "error" in x: print(f"    ERR {x['poc']}: {x['error']}")
        else: print(f"    {x['poc'][:34]:34s} crash={x['crash']} preset={x['solved_preset']} cls={x['actual_class']} | {x['actual_frame'][:54]}")
json.dump(out,open(REPO/"tools/offtarget/interference_verified.json","w"),indent=2,default=str)
from collections import Counter
print("\n=== verdicts ==="); [print(f"  {v:22s}{n}") for v,n in Counter(x['verdict'] for x in out).most_common()]
