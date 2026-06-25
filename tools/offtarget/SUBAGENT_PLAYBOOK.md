# Off-target suppression — per-bug playbook (for build agents)

## Goal
Author a minimal source patch that makes the bug's **new V1** binary:
- **P1** NOT fault on the catalogued off-target PoC(s)  (the interference is removed)
- **P2** STILL fault on the preset PoC, same class/site  (the preset bug is untouched)
while changing program LOGIC as little as possible (this is an experiment's independent variable).

You succeed when `tools/offtarget/build_and_verify.py <bug_id> --patch <p>` prints **VERDICT: PASS**.

## Inputs you have
- `tools/offtarget/inventory.json` — your bug's off-target entry (ot_class, ot_frame, poc_files, bucket).
- Off-target report dir: `/data4/ze/O2_Vulnerability_Management/incoming_report/offtarget-*` —
  contains `repro.yaml`/`vuln.yaml` (off-target crash site/class), `backtrace_*.txt`, and `poc/`.
- Preset truth: `bugs/<proj>/<bug>/grader/expected.yaml` (preset class/site) and `bench.yaml`
  (vuln_commit, fix_commit, invocation).
- Preset PoC: `bugs/<proj>/<bug>/poc/poc.bin`.

## Get the source at vuln_commit
Either: `curl -s https://raw.githubusercontent.com/<owner>/<repo>/<vuln_commit>/<path>` (network works),
OR run one build attempt and read the materialized tree at
`delta-bisect/src-cache/<bug_id>/ctx-<sha12>/__srctree__/...` (build_at leaves it on disk).

## Patch mechanism BY BUCKET
- **ubsan** (off-target is a UBSan "runtime error"): add `__attribute__((no_sanitize("<CHECK>")))`
  to the off-target function, scoped to the off-target's CHECK TYPE only
  (`signed-integer-overflow`, `shift`, `null`, `alignment`, `bounds`, ...). If the preset is also
  UBSan, make sure your check ≠ the preset's check so the preset still fires. PROVEN on dtc.
- **leak** (LSan): the off-target leak is a different alloc-site than the preset. Bake a scoped
  LSan suppression into the binary by adding a C/C++ file defining:
  `extern "C" const char *__lsan_default_suppressions(void){ return "leak:<offtarget_func>\n"; }`
  (compile it into the harness). This suppresses ONLY that leak; the preset leak still reports.
  Find the harness link step in `bugs/<proj>/<bug>/harness/build.sh` and add the file.
- **memcorruption** (segv / heap-buffer-overflow / heap-use-after-free): NOT sanitizer-suppressible —
  the input actually corrupts memory. Apply the OTHER bug's real fix: find the upstream commit/PR
  that fixed THIS off-target (check the report's repro.yaml `submission.link`), or add a minimal
  bounds/null guard at the off-target frame so the bad input is rejected before the corruption.
  Keep it surgical. The preset path must be unaffected (verify P2).
- **stack-overflow / stack-exhaustion**: add a recursion-depth guard or input-size cap at the
  off-target recursion site so it returns cleanly instead of exhausting the stack.
- **assert / abort**: the off-target is a reachable assert/abort. Replace that specific assert with
  a graceful early-return (or guard its precondition). Do NOT disable asserts globally.
- **java uncaught-exception**: wrap the off-target call site so the specific exception type is caught
  and handled (return/skip) instead of propagating. Patch the harness or the library method on the
  off-target frame. The preset exception/oob must still propagate.
- **oom**: usually a libFuzzer rss_limit / -Xmx resource artifact, NOT a distinct defect. First check
  whether it even faults under the grade env (run the driver). If P1 already holds with NO patch
  (empty/no-op), report that — the off-target does not interfere on the benchmark binary.

## Iterate
1. Write `tools/offtarget/patches/<bug_id>.patch` (unified diff, `-p1` from repo root of the SOURCE,
   i.e. paths like `a/src/foo.c`). Include a short prose header above the diff (the driver's
   `git apply`/`patch -p1` skip it).
2. Run: `.venv/bin/python tools/offtarget/build_and_verify.py <bug_id> --patch tools/offtarget/patches/<bug_id>.patch`
   (add `--leak` for the leak bucket so detect_leaks=1 in the verify env).
3. Read `tools/offtarget/results/<bug_id>.json` for per-check detail. Fix and repeat until PASS.

## Rules
- Touch ONLY `tools/offtarget/patches/<bug_id>.patch` (and a tiny new source file IF the bucket
  needs one, referenced via the patch). Do NOT edit other bugs, the grader, or commit anything.
- If you cannot reach PASS, STOP and report: the exact failing property, the off-target/preset
  behavior you observed, and what you tried. Honest FAIL > fake PASS.
- Report back: final verdict, the patch you wrote, and the mechanism used.
