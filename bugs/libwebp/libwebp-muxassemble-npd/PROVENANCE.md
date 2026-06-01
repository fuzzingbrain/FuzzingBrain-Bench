# Provenance — libwebp-muxassemble-npd

- **Upstream report:** https://issues.webmproject.org/issues/497882857
- **Fix commit:** `0c9546f7efc61eac7f79ae115c3f99c91c21c443` (chromium-review
  https://chromium-review.googlesource.com/c/webm/libwebp/+/7718201) — adds the NULL
  guard in muxedit.c and expands the muxer fuzzer.
- **vuln_commit:** `b8814a57f0e010969b0d9352d86fa30b855d3fa0` (parent of the fix) — bug PRESENT.
  Confirmed via `gh`: 0c9546f7 modifies src/mux/muxedit.c, muxinternal.c, demux.c + fuzzer.
- **CVE:** none. Severity high. Discovered 2026-03-21, submitted 2026-03-30, fixed 2026-04-01.
- **Discovery:** FuzzingBrain-V2 / O2 (chromium libwebp arm).
- **Origin record:** `O2_Vulnerability_Management/projects/chromium/null-deref-WebPMuxAssemble/`

## Root cause

`WebPMuxCreate()` parses a malformed animated WebP with corrupted ANMF frames where
`wpi->img_` is NULL. `WebPMuxAssemble()` accesses frame info through that NULL pointer in
`GetFrameInfo` (muxedit.c:407) without checking. Reachable through the public mux API on
attacker-supplied bytes; 3 crash WebP inputs found (one is this bundle's poc.bin).

## Harness

`webp_mux_fuzzer.c` — libFuzzer driver over the public `webp/mux.h` API: `WebPMuxCreate`
from the input, query/set chunks and frames, then `WebPMuxAssemble`. Public-API path, not a
hand-built invalid state — passes the FP screen. The oracle's site line is keyed to this
bundle's actual ASan output at the pinned vuln_commit.
