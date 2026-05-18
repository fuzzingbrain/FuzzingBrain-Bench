# pdfbox-cmap-bfrange-aioob harness provenance

- **Source**: PR body of https://github.com/apache/pdfbox/pull/411 — section "Trigger Method 2: Direct API" provides a small Java reproducer driver. **No Jazzer fuzzer harness is attached**.
- **URL fragment**: https://github.com/apache/pdfbox/pull/411#issue
- **Found in**: issue_body (direct-API repro only)
- **Notes**: PR also includes a Python script `create_malicious_pdf_cmap.py` for crafting the PoC PDF; no fuzz target. Bench-corpus.json best-guess for OSS-Fuzz harness is unspecified; PR does not link a Jazzer harness.
