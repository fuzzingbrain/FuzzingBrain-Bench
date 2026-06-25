import json, glob, os, tempfile, shutil
from fbbench.grading.bench_yaml import capability_set, find_bug
from fbbench.paths import REPO
from fbbench.runner.mcp_client import MCPClient, stage_bug_view
server=str(REPO/"bin"/"mcp-server")
OT="/data4/ze/O2_Vulnerability_Management/incoming_report"
inv=json.load(open("tools/offtarget/inventory.json"))
otmap={}
for e in inv:
    bug=e["bundle"].split("/")[-1]
    otmap.setdefault(bug,[]).extend(os.path.join(OT,p) for p in e.get("poc_files",[]))
bugs=sorted((d.split("/")[-1], d.split("/")[1]) for d in glob.glob("bugs-armB/*/*"))
def grade1(oracle, poc, bug):
    bd=find_bug(bug,REPO); ws=tempfile.mkdtemp(); view=stage_bug_view(str(bd),full_scan=False)
    try:
        m=MCPClient(server,bug_dir=view,workspace=ws,oracle_dir=oracle); m.initialize(); m.call("setup",{})
        dst=os.path.join(ws,os.path.basename(poc)); shutil.copy2(poc,dst)
        return set(k for k,v in m.call("grade",{"path":dst}).get("capabilities",{}).items() if v=="fired")
    finally: shutil.rmtree(ws,ignore_errors=True); shutil.rmtree(view,ignore_errors=True)
out=[]; allok=True
for bug,proj in bugs:
    armA=str(REPO/"bugs"/proj/bug); armB=str(REPO/"bugs-armB"/proj/bug)
    kb=set(capability_set(REPO/"bugs"/proj/bug))
    ots=[p for p in otmap.get(bug,[]) if os.path.exists(p)]
    rec={"bug":bug,"offtarget":[]}
    for p in ots:
        ca=grade1(armA,p,bug); cb=grade1(armB,p,bug)
        rec["offtarget"].append({"poc":os.path.basename(p),"A_crash":"crash" in ca,"B_crash":"crash" in cb})
    pp=str(REPO/"bugs"/proj/bug/"poc"/"poc.bin")
    if os.path.exists(pp):
        pa=grade1(armA,pp,bug); pb=grade1(armB,pp,bug)
        rec["preset_A_solved"]=kb.issubset(pa); rec["preset_B_solved"]=kb.issubset(pb)
    ot_ok=all(o["A_crash"] and not o["B_crash"] for o in rec["offtarget"]) if rec["offtarget"] else False
    pr_ok=rec.get("preset_B_solved",False)
    rec["verdict"]="OK" if (ot_ok and pr_ok) else "CHECK"
    if rec["verdict"]!="OK": allok=False
    out.append(rec)
    print(f"{bug:40s} OT:{[(o['A_crash'],o['B_crash']) for o in rec['offtarget']]} preset A={rec.get('preset_A_solved')} B={rec.get('preset_B_solved')} -> {rec['verdict']}", flush=True)
json.dump(out, open("tools/offtarget/eval_data/arm_integrity_audit.json","w"), indent=2)
print("\nALL CLEAN" if allok else "\n*** SOME NEED ATTENTION ***")
