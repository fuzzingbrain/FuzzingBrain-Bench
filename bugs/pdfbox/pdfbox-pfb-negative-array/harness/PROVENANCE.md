# pdfbox-pfb-negative-array harness provenance

- **Source**: PR body of https://github.com/apache/pdfbox/pull/412 — section "Trigger Method 2: Direct API" provides a small Java reproducer driver. **No Jazzer fuzzer harness is attached.**
- **URL fragment**: https://github.com/apache/pdfbox/pull/412#issue
- **Found in**: issue_body (direct-API repro only)
- **Notes**: PR references a Python `create_malicious_pdf_pfb.py` for crafting the trigger PDF and provides the raw 18-byte PFB hex; no fuzz target source.
