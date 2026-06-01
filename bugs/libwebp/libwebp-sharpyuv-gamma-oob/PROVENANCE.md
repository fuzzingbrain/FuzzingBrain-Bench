# Provenance — libwebp-sharpyuv-gamma-oob

- **Upstream advisory:** https://github.com/webmproject/libwebp/security/advisories/GHSA-6gpr-h4hq-vh57
- **Status:** fixed (chrome submissions dashboard `fixed`; verified 2026-04-24 encode-side scope).
- **vuln_commit:** `b8814a57f0e010969b0d9352d86fa30b855d3fa0` — the missing-clamp bug is PRESENT.
- **CVE:** none. high (encoder/transcoder reach; not browser-side decode).
- **Discovery:** O2 / FuzzingBrain chrome libwebp arm.
- **Origin record:** `O2_Vulnerability_Management/projects/libwebp/oob-read-libwebp-sharpyuv-gamma-lut/`
  + root `repro_sharpyuv.cpp`.

## Root cause

`SharpYuvConvert` -> `DoSharpArgbToYuv` -> `ImportOneRow`/`UpdateW` -> `SharpYuvGammaToLinear`
-> `ToLinearSrgb` -> `FixedPointInterpolation` (sharpyuv/sharpyuv_gamma.c:91). High-bit-depth
(`rgb_bit_depth >= 10`) pixel samples are not clamped to `(1<<rgb_bit_depth)-1`; an out-of-range
`uint16_t` value produces a `tab_pos` that walks past the static `kGammaToLinearTabS` LUT — OOB read.

## PoC (crafted from the public-API repro)

No upstream crash file shipped; the PoC is crafted from the documented trigger and the reference
`repro_sharpyuv.cpp` parsing layout: width=2, height=2, `rgb_bit_depth=10`, and 0xFFFF pixel
samples (>1023) → deterministic OOB. The harness `sharpyuv_convert_fuzzer.cc` is the libFuzzer
form of that public-API repro (`SharpYuvConvert`). Public-API path — passes the FP screen.
Oracle keyed to this bundle's actual ASan output (SEGV at sharpyuv_gamma.c:91).
