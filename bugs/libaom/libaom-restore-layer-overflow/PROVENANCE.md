# Provenance — libaom-restore-layer-overflow

- **Upstream report:** https://issues.chromium.org/issues/501657371 (CVSS S1 / high)
- **Fix:** aomedia-review CL https://aomedia-review.googlesource.com/210741, chromium roll
  https://chromium-review.googlesource.com/7790046 (fixed 2026-04-23). Roll was
  `f23c9437a..19777f051`.
- **vuln_commit:** `f23c9437a` (lower bound of the fix roll) — bug PRESENT (pre-fix).
- **CVE:** none assigned. Discovered 2026-04-11, confirmed 2026-04-14, fixed 2026-04-23.
- **Discovery:** O2 Security Team (FuzzingBrain), chrome/libaom arm. status `fixed`
  (`triage_status: fixed_upstream`, `adoption: true`).
- **Origin record:** `O2_Vulnerability_Management/projects/libaom/heap-overflow-av1-restore-layer-context/`
  and `data/chrome/libraries/libaom/harnesses/libaom_ratectrl_rtc_interface/`.

## Root cause

Buffer allocation in `av1_alloc_layer_context` does not fully account for certain
spatial/temporal layer combinations. When `AV1RateControlRTC::ComputeQP` calls
`av1_restore_layer_context`, a `memcpy` reads more bytes than the destination buffer
holds → heap-buffer-overflow.

## Harness (FP screen)

`libaom_ratectrl_rtc_interface_fuzzer.cc` mirrors the real WebRTC caller
(`libaom_av1_encoder.cc`): `Create(cfg)` → `UpdateRateControl(cfg)` → `ComputeQP(frame)`
→ `PostEncodeUpdate(size)`. It deliberately keeps `target_bandwidth > 0` and the
buffer-size inequalities valid so it does NOT trip the well-known harness-author
divide-by-zero — it exercises the real layer-context overflow on the public interface.
Passes the FP screen. Oracle site/class keyed to this bundle's actual ASan output.

## Build note

libaom builds via cmake (encoder + RTC). The `AV1RateControlRTC` interface lives in the
separate `aom_av1_rc` target (`libaom_av1_rc.a`), linked alongside `libaom.a`.
