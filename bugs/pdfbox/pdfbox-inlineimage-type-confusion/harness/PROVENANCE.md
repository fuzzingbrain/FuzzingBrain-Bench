# pdfbox-inlineimage-type-confusion harness provenance

- **Source**: PR body of https://github.com/apache/pdfbox/pull/410 — section "Trigger Method 2: Direct API" provides a small Java reproducer driver. **No Jazzer fuzzer harness is attached.**
- **URL fragment**: https://github.com/apache/pdfbox/pull/410#issue
- **Found in**: issue_body (direct-API repro only)
- **Notes**: PR also has a Python `create_malicious_pdf_inline.py` for crafting the trigger PDF. No fuzz target source in the report.
