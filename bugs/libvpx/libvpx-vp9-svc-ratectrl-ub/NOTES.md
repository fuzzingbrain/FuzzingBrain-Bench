# NOTES — gaps and caveats (libvpx-vp9-svc-ratectrl-ub)

Binaries were NOT built or validated in this benchmark copy (NO docker / NO
compile per task brief). Real, known caveats:

1. **UBSan-only finding.** ASan alone does not flag the NaN->int cast. The
   asan library build and the asan harness configs add
   `-fsanitize=undefined -fno-sanitize-recover=undefined` (see harness/build.sh).
   An NDEBUG ASan-only build runs cleanly (exit 0). UBSan reports
   `vpx_dsp/vpx_dsp_common.h:89:10: runtime error: -nan is outside the range of
   representable values of type 'int'`.

2. **Debug-build secondary signal.** On a build configured with
   `--enable-debug` (as the original discovery tree was), the harness-side
   signal is the debug-only `assert(ctx->pending_frame_count)` at
   `vp9/vp9_cx_iface.c:1282`, NOT the UBSan error. build.sh does NOT pass
   `--enable-debug`, so NDEBUG is the default and the assert is elided — UBSan
   then surfaces the real NaN->int defect. This is a Type-1 ("assert was
   catching a real bug") finding.

3. **PoC source-of-truth.** poc/poc.bin is the actual transferred crash input
   (3627 bytes). The bug report's inline `generate_poc.py` emits a different,
   16-byte MINIMIZED variant (`03 02 ff 07 ff ff 07 07 00...`). Because the two
   differ, no generate_poc.py is shipped for this entry; the real 3627-byte
   crash file is authoritative. (The 16-byte minimized form decodes to the same
   4-spatial x 3-temporal, 64x32, 8-frame SVC config and is documented in the
   bug report if a smaller seed is wanted.)

4. **vuln_commit `3c456eb6...`** taken from method.yaml
   (library_repo_url https://chromium.googlesource.com/webm/libvpx), matching
   the bug report's Production Reproduction clone.

5. **Site frame.** The UBSan-reported location is the cast in
   `saturate_cast_double_to_int` (vpx_dsp_common.h:89); the NaN is produced one
   frame up in `vp9_update_buffer_level_svc_preencode` (vp9_ratectrl.c). The
   grader keys reach/site to the cast site (the UBSan location).
