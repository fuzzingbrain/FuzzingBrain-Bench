# NOTES — gaps and caveats (skia-raster8888-blur-oob)

Binaries were NOT built or validated in this benchmark copy (NO docker / NO
compile per task brief). The following gaps are material and a benchmark
operator should weigh them before relying on this entry's build:

1. **BUILD-SIZE RISK — skia is a very large build (primary caveat).**
   A free-standing `clang++ ... -lskia` link is unworkable: `libskia.a`
   transitively pulls in dozens of in-tree libraries (skcms, harfbuzz, freetype,
   ICU, libc++, abseil, etc.) not exposed as a single archive. The faithful path
   is Skia's GN/Ninja graph, which requires `tools/git-sync-deps` (multi-GB
   third_party + bundled clang sync) and a long, memory-hungry `ninja skia`
   build. The provided `harness/build.sh` + `Dockerfile` encode that path but
   **may be infeasible to build in a standard CI box**, and they were not
   executed here. The original O2 reproduction did not link standalone Skia at
   all — it registered the repro as an `executable()` target inside chromium's
   `custom_fuzzers/BUILD.gn` and built it with the whole chromium GN graph
   (binary ~160 MB). That chromium-GN path is the only one actually validated
   upstream; reproducing it standalone is the open build problem.

2. **Exact vuln_commit may not be fetchable.**
   `vuln_commit d3ea842c93e59fec607736bd605f77216264483e` is the skia
   `upstream_commit` recorded in the source record's `build_info.yaml` (the
   commit the harness was built against). It is a chromium-rolled skia revision
   and was NOT resolvable from the public `skia.googlesource.com` shallow CDN nor
   the github.com/google/skia mirror at authoring time (both returned NOT_FOUND
   for that object). Any skia/main commit strictly before the fix (CL 1225736 /
   commit d2740c899a1ec8a22209840bd8350f22f8c27ecf) still carries the
   unpatched `eval_blur_passes` X->Y rebind getAddr and should reproduce; the
   Dockerfile falls back to that guidance if the exact SHA cannot be checked out.

3. **dcheck vs. silent OOB.**
   In the upstream/chromium fuzz config (`dcheck_always_on=true`) the bug
   surfaces as a fatal `SkASSERT` at SkBitmap.cpp:387 (the symbolized trace in
   the record). In release/no-assert builds `getAddr` silently returns an OOB
   pixel pointer that the blur loop dereferences — the real memory-safety bug,
   class `out-of-bounds-access`, sanitizer `asan`. To make ASan flag the OOB
   read/write itself (rather than only the assert), build WITHOUT the assert
   being a fatal abort and rely on ASan's shadow on the bitmap allocation; the
   provided build.sh uses an ASan config for this reason. This was not validated.

4. **PoC selection.**
   `poc/poc.bin` is the 24-byte crash input that lives in the source record
   proper. The record also carries a separate `.repro/` Path-B bundle with a
   17-byte input (`crash-a3769e...`) that was driven through an inline
   re-implemented FuzzedDataProvider; that variant is NOT used here because this
   entry ships the original libFuzzer harness, whose FuzzedDataProvider byte
   layout matches the 24-byte record input.
