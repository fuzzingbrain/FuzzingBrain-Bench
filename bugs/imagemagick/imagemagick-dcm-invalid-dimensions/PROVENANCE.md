# Provenance

**Bug**: Missing final dimension check in `ReadDCMImage` returns zero-size image
**Upstream**: https://github.com/ImageMagick/ImageMagick/security/advisories/GHSA-8pj9-6897-74xc
**CVE**: CVE-2026-49218
**Vuln commit**: 6a10c829fb645e0de1408030e6e0f67e820b0c98 (ImageMagick 7.1.2-23)
**Fix commit**: 84fbcef8a558b1da075417a89d29aa5632d57f63

## Harness

Adapted from the O2Lab AGF `encoder_dcm_fuzzer` path (`fuzzer.cpp` in the O2
bug package). Uses MagickCore `BlobToImage` with `dcm:` and asserts non-zero
geometry on every decoded frame.

## Triggering input

`poc/poc.bin` is the minimized AGF crash input (from the O2 trajectory). The
original trajectory folder is linked in the O2 `vuln.yaml`; import via
`import_poc.sh` if re-sourcing from Drive.

## K_b

`capability_set: [reach, crash, crash2, class, site]`. `class` is `abrt`
(libFuzzer assertion abort when zero-dimension geometry is returned). `site`
targets the final return path of `ReadDCMImage` in `coders/dcm.c`.
