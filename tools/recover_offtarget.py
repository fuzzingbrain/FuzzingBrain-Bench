#!/usr/bin/env python3
"""Recover crashing PoC blobs from a full-scan run's transcript.jsonl.

For a given run dir (…/<bug>/<model>/seed-N) reconstructs the workspace by
replaying write_file contents, then for every grade() call whose harness_output
indicates a crash, dumps the input bytes and the sanitizer evidence.

Note: only files materialised via write_file are recoverable here; files an
agent created via `exec` (printf/python/base64) are flagged as exec-origin.
"""
import json, sys, os, hashlib

def is_crash(res):
    if not isinstance(res, dict):
        return False
    h = res.get('harness_output', res)
    sig = h.get('signal', '') or ''
    ec = h.get('exit_code', 0)
    se = h.get('stderr', '') or ''
    if sig:
        return True
    if ec not in (0, None):
        return True
    if 'SUMMARY: ' in se or 'runtime error:' in se or 'ERROR: libFuzzer' in se:
        return True
    if 'AddressSanitizer' in se or 'LeakSanitizer' in se or 'UndefinedBehaviorSanitizer' in se:
        return True
    return False

def main(run_dir, out_dir=None):
    tpath = os.path.join(run_dir, 'transcript.jsonl')
    lines = [json.loads(l) for l in open(tpath)]
    tools = [l for l in lines if l.get('event') == 'tool_result']

    # replay filesystem: path -> bytes (write_file only); track exec-touched paths
    fs = {}
    exec_touched = set()
    crashing = []  # (turn, path, content_or_None, stderr)

    for t in tools:
        tool = t['tool']; inp = t['input']
        if tool == 'write_file':
            fs[inp['path']] = inp.get('content', '')
        elif tool == 'exec':
            cmd = json.dumps(inp.get('cmd', inp))
            # crude: if exec redirects/writes to a file, mark workspace paths dirty
            if '>' in cmd or 'printf' in cmd or 'base64' in cmd or 'python' in cmd:
                exec_touched.add(t['turn'])
        elif tool == 'grade':
            res = t['result']
            if is_crash(res):
                path = inp.get('path')
                h = res.get('harness_output', res) if isinstance(res, dict) else {}
                content = fs.get(path)  # None if not from write_file
                crashing.append((t['turn'], path, content, h.get('stderr', '')))

    print(f"# {run_dir}")
    print(f"# crashing grade calls: {len(crashing)}")
    for turn, path, content, stderr in crashing:
        origin = 'write_file' if content is not None else 'EXEC-ORIGIN (not recoverable from write_file)'
        n = len(content) if content is not None else '?'
        print(f"\n## turn {turn}  path={path}  bytes={n}  origin={origin}")
        # crash signature lines
        for ln in stderr.splitlines():
            if any(k in ln for k in ('SUMMARY:', 'ERROR:', 'runtime error', '#0 ', '#1 ', '#2 ', 'in mg_', 'in avro_', '.c:', '.cpp:', '.rs:')):
                print('   |', ln.strip()[:160])
        if out_dir and content is not None:
            os.makedirs(out_dir, exist_ok=True)
            fn = os.path.join(out_dir, f"turn{turn}_{os.path.basename(path)}")
            with open(fn, 'w') as f:
                f.write(content)
            print(f"   -> saved {fn}  sha1={hashlib.sha1(content.encode()).hexdigest()[:12]}")
    if exec_touched:
        print(f"\n# NOTE: exec turns that may have created/modified files: {sorted(exec_touched)}")

if __name__ == '__main__':
    main(sys.argv[1], sys.argv[2] if len(sys.argv) > 2 else None)
