import glob, os, json, shutil, tempfile, sys
from fbbench.grading.bench_yaml import capability_set, find_bug
from fbbench.paths import REPO
from fbbench.runner.mcp_client import MCPClient, stage_bug_view

model="claude-haiku-4-5"; level="diff-0"
server=str(REPO/"bin"/"mcp-server")
results=[]
dirs=sorted(glob.glob(f"runs/diffscan/*/{model}/{level}"))
for d in dirs:
    bug=d.split("/")[2]
    pocs=sorted(glob.glob(f"{d}/pocs/**/*.bin",recursive=True))
    bug_dir=find_bug(bug,REPO)
    if not pocs or bug_dir is None: 
        results.append((bug,0,[],False,"no blobs")); continue
    kb=set(capability_set(bug_dir))
    ws=tempfile.mkdtemp(); view=stage_bug_view(str(bug_dir),full_scan=False)
    try:
        mcp=MCPClient(server,bug_dir=view,workspace=ws,oracle_dir=str(bug_dir))
        mcp.initialize(); mcp.call("setup",{})
        best=set()
        for b in pocs:
            dst=os.path.join(ws,os.path.basename(b)); shutil.copy2(b,dst)
            try: caps=mcp.call("grade",{"path":dst}).get("capabilities",{})
            except Exception: continue
            best|={k for k,v in caps.items() if v=="fired"}
        solved=bool(kb) and kb.issubset(best)
        results.append((bug,len(best),sorted(best),solved,""))
        print(f"  {bug:38s} fired={sorted(best)} solved={solved}",flush=True)
    finally:
        shutil.rmtree(ws,ignore_errors=True); shutil.rmtree(view,ignore_errors=True)

solved=sum(1 for r in results if r[3])
crashed=sum(1 for r in results if "crash" in r[2])
offt=[r[0] for r in results if "crash" in r[2] and not r[3]]
print("\n"+"="*60)
print(f"REGRADE (fixed grader) haiku diff-0: {len(results)} bugs")
print(f"  solved(K_b)={solved}  crash={crashed}  off-target={len(offt)}")
print(f"  off-target: {offt}")
json.dump([{'bug':r[0],'fired':r[2],'solved':r[3]} for r in results],
          open("runs/diffscan/_regrade_haiku_diff0.json","w"),indent=2)
