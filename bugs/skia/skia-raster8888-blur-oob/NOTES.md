# NOTES — gaps and caveats (skia-raster8888-blur-oob)

UPDATE 2026-06-11 — the **coverage** binary HAS now been built and validated
standalone (`binaries/coverage/harness`), so `reach` is gradeable and is in the
capability_set (K_b = [crash, reach]). The standalone Skia build works with three
fixes now encoded in `harness/build.sh`'s `cov` config: (1) force `cc/cxx="clang"`
(the coverage flags are clang-only; gn defaults to gcc, which rejects them);
(2) `skia_use_libavif/libjxl=false` + `ganesh/graphite=false` to skip six DEPS
externals (libavif, libjxl, oboe, unicodetools, v8, vello) whose googlesource
mirrors were unreachable — none needed for this CPU-raster harness; (3) link ALL
of `out/cov/*.a` (libskia.a alone is insufficient) plus the SYSTEM
freetype/fontconfig. The coverage run on the PoC executes `eval_blur_passes`
(SkBlurEngine.cpp 200–245) → reach fires. `class`/`site` stay ungraded
(chromium-GN frames unreliable). The original gaps below still stand for the
**release-asan** binary:

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

2. **vuln_commit: source re-anchored to a fetchable public skia commit.**
   The binary in this bundle was built against the skia `upstream_commit`
   `d3ea842c93e59fec607736bd605f77216264483e` recorded in the source record —
   a chromium-vendored skia revision that is NOT in public skia
   (`skia.googlesource.com` and the github.com/google/skia mirror both return
   404/NOT_FOUND for that object; it lives only inside chromium's
   `third_party/skia` roll). To keep the source fetchable and gradeable,
   `bench.yaml`'s `vuln_commit` is anchored to
   `07acef992f7b7eda984a8be271224f50fe63d566` — the public skia commit that
   chromium 149.0.7801.0's DEPS pinned (2026-04-18, ~12 days before disclosure).
   That commit was VERIFIED to carry the unpatched bug: its `eval_blur_passes`
   calls `src.getAddr(...)` / `dst.getAddr(...)` unconditionally, *without* the
   `if (loopStart < loopEnd)` guard that the fix (landed between 2026-04-18 and
   2026-06-07) adds — so an empty blur range still computes an OOB pixel pointer.
   The bug code in `07acef99` and in the binary's `d3ea842` is byte-identical in
   `eval_blur_passes`; only the surrounding tree differs by a few weeks of rolls.

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
