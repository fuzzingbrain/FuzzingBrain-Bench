# openssl-des-ofb-cfb-overread harness provenance

- **Source**: Issue body of https://github.com/openssl/openssl/issues/30284 — sections "Method 2: Standalone PoC" (`poc_standalone.c`) and "Method 2: Full OpenSSL EVP API PoC" (`poc_evp_api.c`). Method 1 references a fixed `fuzz/provider.c` ("`provider_fixed.c` (drop-in replacement for `fuzz/provider.c`)") but **the fixed harness source is not pasted in the issue** — only described.
- **URL fragment**: https://github.com/openssl/openssl/issues/30284#issue
- **Found in**: issue_body (two C PoC drivers; the fuzz harness itself only described in prose)
- **Notes**: The discovery harness `provider_fixed.c` (a fix of upstream `fuzz/provider.c` — closing #30281) is described by its diff intent but not pasted verbatim. PR #30332 (the fix) does not contain the harness either. Saving the two C drivers; the actual fuzzer source needs human follow-up to retrieve (likely from FuzzingBrain's internal CRS workspace).
