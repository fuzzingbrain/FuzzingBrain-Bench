# imagemagick-msl-stack-overflow harness provenance

- **Source**: Advisory body of https://github.com/ImageMagick/ImageMagick/security/advisories/GHSA-9vj4-wc7r-p844 — section "Fuzzer". Identical harness to imagemagick-msl-comment-npd.
- **URL fragment**: GHSA-9vj4-wc7r-p844 (advisory body)
- **Found in**: advisory_body
- **Notes**: Same MSL libFuzzer harness as the other ImageMagick MSL bug. The harness depends on `utils.cc` (defines `IsInvalidSize`) which is the standard ImageMagick fuzz helper not pasted inline.
