# Run report — adding Fixed crash bugs from O2 / agf-results (2026-06-01)

Expanded FuzzingBrain-Bench from **37 → 48** end-to-end gradeable bugs. Every added bug
is a **3-round unanimous PASS** (`./fb-bench grade <id>`), built reproducibly via its
`Dockerfile`, sourced from upstream-**Fixed** crash vulnerabilities in the O2 records
(primarily `agf-results/`, the AI-Guided Fuzzing arm, plus the chrome submissions arm).

## Added (11) — all grade = PASS

| # | bug_id | project | class | K_b | vuln_commit | source / upstream |
|---|---|---|---|---|---|---|
| 38 | libpng-zlib-inflate-uaf | libpng | use-after-free | R C Cl S | 614ab644 | CVE-2026-46675 · GHSA-qvg3-h654-xq3j |
| 39 | libheif-image-crop-overflow | libheif | heap-buffer-overflow | R C Cl S | 62f1b8c7 | strukturag/libheif#1746 |
| 40 | imagemagick-kernelinfo-alloc | imagemagick | allocation-size-too-big | R C S | 3c45ab0b | GHSA-q62c-h75r-2xhc |
| 41 | spirv-orderblocks-segv | spirv-tools | segv / oob-write | R C Cl S | ff5c5033 | KhronosGroup/SPIRV-Tools#6663 (PR #6676) |
| 42 | libwebp-muxassemble-npd | libwebp | null-deref | R C Cl S | b8814a57 | webmproject #497882857 (fix 0c9546f7) |
| 43 | libwebp-sharpyuv-gamma-oob | libwebp | oob-read | R C Cl S | b8814a57 | GHSA-6gpr-h4hq-vh57 |
| 44 | icu-translit-rule-dtor-uaf | icu | use-after-free | R C Cl S | 8be6575f | ICU-23365 (fixed 79.1) |
| 45 | libaom-restore-layer-overflow | libaom | heap-buffer-overflow | R C Cl S | f23c9437a | chromium #501657371 (aom CL 210741) |
| 46 | libaom-av1-config-assert | libaom | assertion-failure | R C S | f23c9437a | aom_rb_read_literal assert(bits<=31) |
| 47 | opcua-pubsub-json-assert | open62541 | assertion-failure | R C S | 0b75ea2c | open62541 PR #7680 |
| 48 | libvpx-vp9-reconfig-overflow | libvpx | heap-buffer-overflow | R C Cl S | a5e2e652 | webmproject #501696590 |

K_b legend: R=reach C=crash Cl=class S=site. Bugs without a `Cl` flag are
`allocation-size-too-big` / plain-`assert()`-abort classes for which the oracle has no
sanitizer class token; they grade on reach + crash + site (the bug's `capability_set`
declares this, mirroring existing bench bugs like `freerdp-ntlm-memleak`).

## Validation

- All 11 new bugs: `./fb-bench grade <id>` → **PASS, agreed=True**, every K_b flag fired.
- Regression spot-check (jq-dump-op-npd, mongoose-mg-match-overflow, netsnmp-vacm-parse-npd): PASS.
- `./fb-bench list` → **48 bugs available**.

## Notes for reproduction

- Each bundle builds self-contained binaries via `docker build`; heavy decoder deps are
  statically linked (libheif↔libde265, libaom RateControlRTC ↔ aom_av1_rc) so extracted
  binaries run anywhere.
- Several null-deref/UAF bugs are built **ASan-only** (UBSan would abort first with no
  backtrace, defeating site/reach); the detected class is `segv` for those.
- libwebp is built `-DNDEBUG` (production path) so the real null-deref surfaces instead of an
  internal assert; libaom-av1-config is built **with asserts on** because the bug *is* the assertion.
