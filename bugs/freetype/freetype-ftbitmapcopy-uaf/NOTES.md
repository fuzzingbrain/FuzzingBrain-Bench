# Notes / provenance — freetype-ftbitmapcopy-uaf

## Source record
`O2_Vulnerability_Management/projects/freetype/heap-use-after-free-FT_Bitmap_Copy-20260127/`

- Upstream: https://gitlab.freedesktop.org/freetype/freetype/-/issues/1385
- Fix commit: `85c8efe0af` ("ft_bitmap_glyph_init: Always copy in full. ... Fixes #1385.")
- Discoverer: Jeff @ O2 Security Lab (FuzzingBrain).

## Harness — PRESENT, copied verbatim
`harness/ftfuzzer_glyph.c` is copied byte-for-byte from the record's
`ftfuzzer_glyph.c` (FuzzingBrain-generated glyph fuzzer, Apache-2.0 header from
Google's oss-fuzz template). It is NOT FreeType's stock oss-fuzz `ftfuzzer.cc`;
the record uses this custom glyph-iteration harness because the UAF needs two
FT_Get_Glyph calls on a rendered slot, which the stock harness does not perform.
The grader call-stack (ftfuzzer_glyph.c:142 FT_Get_Glyph) matches this harness.

## PoC — PRESENT, copied verbatim
`poc/poc.bin` is the record's `crash_input.bin` (5830 bytes). The record's
vuln.yaml refers to it as `x_9c83518a.bin`; only `crash_input.bin` is present in
the record and that is what was copied.

## vuln_commit — DERIVED (gap in record)
The record does NOT pin an exact commit: vuln.yaml/issue.md say only
"Latest (tested on current master)". I resolved a real, verifiable pre-fix
commit = the **parent of the fix** `85c8efe0af`:
  vuln_commit = d41d4943410cb942e02e0a8866f39be02378ecf5  (2026-02-07, bug PRESENT)
This is the faithful "bug present" state immediately before the fix. Hashes are
identical between the canonical gitlab.freedesktop.org repo and the
github.com/freetype/freetype mirror used in the Dockerfile.

## Grader site
ASan trace (report.md / VERIFY.md):
  #0 __asan_memcpy ; #1 FT_Bitmap_Copy src/base/ftbitmap.c:123:9
Faulting library frame = FT_Bitmap_Copy @ ftbitmap.c:123. (Note: line 123 is the
record's build; FreeType line layout may shift slightly at vuln_commit, hence
line_tolerance: 20.)

## Build notes
FreeType builds with CMake; static, instrumented, all optional deps (zlib/bzip2/
png/harfbuzz/brotli) disabled so the harness binary is self-contained. The smooth
renderer (which allocates the freed bitmap buffer) is built in by default.

## NOT done (per task scope)
No docker build, no compile, no commit. build.sh/Dockerfile are unverified by
execution.
