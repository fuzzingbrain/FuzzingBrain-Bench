"""直接在 Arm-B 的 release-asan/harness 上跑每个原始 off-target PoC,
确认全部不再崩 (exit 0 / 无 sanitizer 报错)。对比 Arm-A 应仍崩。"""
import json, glob, os, subprocess
from pathlib import Path
import yaml
ROOT=Path(".")
OT="/data4/ze/O2_Vulnerability_Management/incoming_report"
inv=json.load(open("tools/offtarget/inventory.json"))
SAN=("ERROR: AddressSanitizer","ERROR: LeakSanitizer","runtime error:","ERROR: libFuzzer",
     "SUMMARY: ","== Java Exception","Exception in thread","AddressSanitizer:","stack-overflow")
def run(binp, poc, inv_args, to=60):
    args=[str(binp)]+[str(poc) if a=="@@" else a for a in (inv_args or ["@@"])]
    env=dict(os.environ); env["ASAN_OPTIONS"]="abort_on_error=1:exitcode=99:detect_leaks=1"
    env["UBSAN_OPTIONS"]="abort_on_error=1:print_stacktrace=1"; env["LSAN_OPTIONS"]="exitcode=99"
    try: p=subprocess.run(args,capture_output=True,text=True,timeout=to,env=env)
    except subprocess.TimeoutExpired: return ("timeout","")
    err=p.stderr or ""
    crashed = (p.returncode not in (0,)) and (any(s in err for s in SAN) or p.returncode in (99,134,135,136,137,138,139,77,71,70))
    return ("CRASH" if crashed else "clean", f"rc={p.returncode}")
rows=[]
for e in inv:
    if e.get("verdict")!="offtarget-confirmed": continue
    bug=e["bundle"].split("/")[-1]; proj=e["bundle"].split("/")[0]
    bd=ROOT/"bugs"/proj/bug
    if not (ROOT/"bugs-armB"/proj/bug).exists(): continue
    bench=yaml.safe_load(open(bd/"bench.yaml")); inv_args=bench["harness"].get("invocation",["@@"])
    for p in e.get("poc_files",[]):
        poc=os.path.join(OT,p)
        if not os.path.exists(poc): continue
        a,_=run(bd/"binaries"/"release-asan"/"harness", poc, inv_args)
        b,_=run(ROOT/"bugs-armB"/proj/bug/"binaries"/"release-asan"/"harness", poc, inv_args)
        ok = (a=="CRASH" and b=="clean")
        rows.append((bug,os.path.basename(p),a,b,ok))
        print(f"{bug:38s} {os.path.basename(p)[:26]:26s} A={a:7s} B={b:7s} {'OK' if ok else '*** CHECK ***'}",flush=True)
nbad=sum(1 for r in rows if not r[4])
print(f"\n{len(rows)} off-target PoCs checked. all-suppressed-in-B: {nbad==0}  (bad={nbad})")
