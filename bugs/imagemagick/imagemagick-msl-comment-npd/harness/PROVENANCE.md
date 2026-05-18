# imagemagick-msl-comment-npd harness provenance

- **Source**: Advisory body of https://github.com/ImageMagick/ImageMagick/security/advisories/GHSA-5vx3-wx4q-6cj8 — section "Fuzzer".
- **URL fragment**: GHSA-5vx3-wx4q-6cj8 (advisory body)
- **Found in**: advisory_body
- **Notes**: libFuzzer harness `msl_fuzzer.cc` (custom MSL fuzzer) that wraps `Magick::Image::read(blob)` with `magick("MSL")`. The reporter notes the harness depends on `utils.cc` (defines `IsInvalidSize`) which is the standard ImageMagick OSS-Fuzz helper at `Magick.NET/coders/utils.cc`-like — not pasted in the advisory.
