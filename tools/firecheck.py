#!/usr/bin/env python3
"""Run a harness on an input, classify the crash (class @ site).

Usage: firecheck.py <harness> <input> [--leaks] [--java]
Prints one line: <FIRE|no-crash>\t<class>\t<site>
"""
import sys, subprocess, re, os

LIB_FUNCS = (r"mg_match|avro_schema_\w+|RuleHalf::parse|hb_calloc|hb_\w+|"
             r"HeifPixelImage::\w+|heif_\w+|OrderBlocks|spvBinaryToText|"
             r"calls_crt1|canPack|PackLinuxElf\w+::\w+|parseBegincodespacerange|"
             r"CodespaceRange")

def classify(out):
    cls = None
    if 'requested allocation size' in out or 'allocation-size-too-big' in out:
        cls = 'allocation-size-too-big'
    if cls is None and re.search(r'(AddressSanitizer:\s*DEADLYSIGNAL|AddressSanitizer: SEGV|\bSEGV on)', out):
        cls = 'segv'
    m = re.search(r'(AddressSanitizer|UndefinedBehaviorSanitizer): ([a-z][a-z-]+)', out)
    if cls is None and m:
        cls = m.group(2)
    if cls == 'requested':
        cls = 'allocation-size-too-big'
    if cls is None and re.search(r'LeakSanitizer: detected memory leaks', out):
        cls = 'memory-leak'
    if cls is None and re.search(r'runtime error:', out):
        cls = 'ubsan-undefined'
    if cls is None and re.search(r'libFuzzer: deadly signal', out):
        # distinguish abort vs segv if possible
        if re.search(r'\babort\b', out):
            cls = 'abort'
        elif 'SEGV' in out or 'segv' in out:
            cls = 'segv'
        else:
            cls = 'deadly-signal'
    if cls is None:
        m = re.search(r'Exception in thread .*?(\w+(?:\.\w+)*(?:Exception|Error))', out)
        if m:
            cls = 'java:' + m.group(1).split('.')[-1]
    # site: prefer a known library frame with file:line
    site = ''
    for ln in out.splitlines():
        m = re.search(r'(?:in |at )?(' + LIB_FUNCS + r')\b', ln)
        if m:
            loc = re.search(r'([\w./+-]+\.(?:c|cc|cpp|rs|java)):(\d+)', ln)
            site = m.group(1) + (' ' + loc.group(1) + ':' + loc.group(2) if loc else '')
            break
    # fallbacks: UBSan "file:line: runtime error", or SUMMARY "... file:line in func"
    if not site:
        m = re.search(r'([\w./+-]+\.(?:c|cc|cpp|rs|java)):(\d+):\d*:?\s*runtime error', out)
        if m:
            site = f"{m.group(1)}:{m.group(2)}"
    if not site:
        m = re.search(r'SUMMARY: \w+: \S+ ([\w./+-]+\.(?:c|cc|cpp|rs|java)):(\d+).*? in (\S+)', out)
        if m:
            site = f"{m.group(3)} {m.group(1)}:{m.group(2)}"
    fired = cls is not None
    return fired, cls or '', site

def main():
    if '--stdin' in sys.argv:
        out = sys.stdin.read()
        fired, cls, site = classify(out)
        print(f"{'FIRE' if fired else 'no-crash'}\t{cls}\t{site}")
        return
    harness, inp = sys.argv[1], sys.argv[2]
    leaks = '--leaks' in sys.argv
    env = dict(os.environ)
    env['ASAN_OPTIONS'] = 'detect_leaks=%d:abort_on_error=0:exitcode=99' % (1 if leaks else 0)
    env['UBSAN_OPTIONS'] = 'print_stacktrace=1'
    try:
        p = subprocess.run([harness, inp], capture_output=True, text=True,
                           timeout=120, env=env)
        out = (p.stderr or '') + (p.stdout or '')
    except subprocess.TimeoutExpired as e:
        se = e.stderr
        if isinstance(se, (bytes, bytearray, memoryview)):
            se = bytes(se).decode('utf-8', 'replace')
        out = (se or '') + '\nlibFuzzer: timeout'
    fired, cls, site = classify(out)
    print(f"{'FIRE' if fired else 'no-crash'}\t{cls}\t{site}")

if __name__ == '__main__':
    main()
