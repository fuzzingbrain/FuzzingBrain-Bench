# NOTES — gaps and caveats (libaom-svc-encoder-hang)

Binaries were NOT built or validated in this benchmark copy (NO docker / NO
compile per task brief). Real, known caveats:

1. **Dual observable signature (timeout vs SIGFPE) — class chosen deliberately.**
   The source record's draft bug report titled this a "hang / infinite recode
   loop" (CWE-835). The verification record (`*.VERIFY.md`) and the repro
   bundle `method.yaml` both RECLASSIFY it: the standalone Path-B public-API
   repro takes a deterministic **SIGFPE (integer divide-by-zero)** inside
   `av1/common/resize.c::interpolate_core` (resize.c:254), reached via
   `av1_realloc_and_scale_if_required -> av1_resize_and_extend_frame_nonnormative
   -> av1_resize_plane -> interpolate`. Under the libFuzzer build, libFuzzer's
   25 s wall-clock alarm preempts the FPE, so the discovery crash was stamped
   `timeout-*` and the harness prints "libFuzzer: timeout after 25 seconds".
   Both signatures are REAL and come from the same (ss=1, ts=2, scale=1/4,
   64x64) config on frame 2. Because the observable depends on whether the
   alarm preempts the FPE, this entry is modeled with the minimal
   `capability_set: [crash, class]` and `class.expected: oom` /
   `sanitizer: libfuzzer` (a resource-exhaustion / timeout-style oracle, per
   the task's steer to model it like an OOM/timeout). The verified SIGFPE site
   (resize.c:254) is recorded in grader/expected.yaml as documentation only;
   reach/site are NOT in capability_set.

2. **vuln_commit source conflict — used method.yaml.**
   The repro bundle `method.yaml` gives `commit_sha:
   a0968d60cf02acfa324af20498634b572baa06a1` (used here, per task instruction
   to take vuln_commit from method.yaml). The bug report's "Production
   Reproduction" section instead cloned
   `b839f927f5d8a448fbcd67b4d434672b9698a3a8`, and the Impact table lists
   `b839f927...` as the affected version. These differ; method.yaml is treated
   as authoritative. A runner that fails to reproduce on a0968d60 should also
   try b839f927.

3. **PoC source-of-truth conflict.**
   The bug report's inline `generate_poc.py` emits a 164-byte buffer (one extra
   leading 0xff). The actual transferred crash file is 163 bytes. poc/poc.bin
   is the real 163-byte crash file; poc/generate_poc.py was rewritten to emit
   exactly those 163 bytes (verified byte-identical).

4. **Build adaptation.**
   This harness drives the full encoder via `aom_codec_av1_cx()`, so build.sh
   only builds/links `libaom.a` (the template `libaom-restore-layer-overflow`
   additionally built `aom_av1_rc` for the standalone RateControlRTC interface,
   which is NOT needed here).

5. **No upstream fix commit pinned for grader.** Fix is
   aomedia-review CL 211381 (merged, per vuln.yaml); exact post-fix SHA not
   recorded.
