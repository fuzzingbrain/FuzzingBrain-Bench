# NOTES — gaps and caveats (libvpx-vpx-img-flip-ub)

Binaries were NOT built or validated in this benchmark copy (NO docker / NO
compile per task brief). Real, known caveats:

1. **UBSan-only finding.** ASan does not flag NULL + non-zero-offset pointer
   arithmetic. The asan library build and asan harness configs add
   `-fsanitize=undefined -fno-sanitize-recover=undefined` (see harness/build.sh).
   UBSan reports `vpx/src/vpx_image.c:263:32: runtime error: applying non-zero
   offset N to null pointer`. A non-UBSan release build runs silently (the
   invalid pointer is parked in the field, never dereferenced).

2. **PoC was synthesized from the bug report (no crash file in record).**
   The transferred O2VM record for this finding carried NO standalone crash
   input file (only bug_report.md / harness / vuln.yaml). poc/poc.bin (14
   bytes) and poc/generate_poc.py are reproduced VERBATIM from the bug report's
   own inline `generate_poc.py`. The bytes decode (via the harness header) to
   format selector -> a non-alpha format (I422) with the `do_flip` bit set,
   width clamped to 8192. generate_poc.py was verified to emit exactly the
   shipped poc.bin.

3. **Trigger requirement.** The bug fires only when (a) the selected format has
   no alpha plane AND (b) the flags byte sets the flip bit so vpx_img_flip is
   actually called. The shipped PoC satisfies both. A reach-only solution that
   allocs but never flips will not trip the UB.

4. **vuln_commit `3c456eb6...`** from method.yaml. Fixed upstream in
   `ca2f535c9ce6fce777864d4ce5b5774516b08978` (chromium-review 7848304).

5. **The concrete UBSan offset varies** with d_h (production driver showed
   2080768; harness wrap path 16646144). The grader keys on the line
   (vpx_image.c:263) and UB class, not the offset value.
