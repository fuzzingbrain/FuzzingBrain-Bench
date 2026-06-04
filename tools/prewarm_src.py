"""Pre-clone all bugs' library source (repo@vuln_commit) into _srccache."""
import glob, os, yaml, time
from concurrent.futures import ThreadPoolExecutor, as_completed
from fbbench.runner.mcp_client import _ensure_source_cache, SRCCACHE
from fbbench.paths import REPO

seen=set(); bugs=[]
for by in sorted(glob.glob(str(REPO/"bugs/*/*/bench.yaml"))):
    b=yaml.safe_load(open(by)) or {}
    t=b.get("target",{}) or {}
    name=os.path.basename(os.path.dirname(by))
    rc=(t.get("repo"), t.get("vuln_commit"))
    if rc[0] and rc[1] and rc not in seen:   # dedup: same repo@commit once
        seen.add(rc); bugs.append((name, rc[0], rc[1]))

print(f"prewarming {len(bugs)} unique repo@commit -> {SRCCACHE}", flush=True)
def work(item):
    name,repo,commit=item
    t=time.time()
    c=_ensure_source_cache(repo,commit)
    return name, c, time.time()-t

ok=fail=0
with ThreadPoolExecutor(max_workers=4) as ex:
    futs={ex.submit(work,it):it[0] for it in bugs}
    for f in as_completed(futs):
        name,c,dt=f.result()
        if c: ok+=1; print(f"  ok   {name:40s} {dt:.0f}s", flush=True)
        else: fail+=1; print(f"  FAIL {name:40s}", flush=True)
print(f"\nDONE: {ok} ok, {fail} fail", flush=True)
