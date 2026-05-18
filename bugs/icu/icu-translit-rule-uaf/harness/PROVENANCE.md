# icu-translit-rule-uaf harness provenance

- **Source**: Jira ticket https://unicode-org.atlassian.net/browse/ICU-23365 — "Method 2 Standalone" reproducer was extracted via WebFetch.
- **URL fragment**: https://unicode-org.atlassian.net/browse/ICU-23365 (Method 2 section)
- **Found in**: bug_body (Jira ticket) — standalone reproducer only; OSS-Fuzz harness for the same code path was not retrievable due to Jira intermittent gating.
- **Notes**: ICU Jira page is intermittently Anubis/login-gated. The reproducer is a small C++ driver that reads a binary file, takes the first byte as a forward/reverse-direction flag, treats the rest as a `UnicodeString` rule, and calls `Transliterator::createFromRules`. bench-corpus.json best-guess `transliterator_fuzzer.cpp` (OSS-Fuzz upstream) is the canonical harness for this code path; its source lives at `icu4c/source/test/fuzzer/transliterator_fuzzer.cpp` in the upstream `unicode-org/icu` repo but is not pasted in the report.
