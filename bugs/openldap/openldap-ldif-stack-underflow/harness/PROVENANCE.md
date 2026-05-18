# openldap-ldif-stack-underflow harness provenance

- **Source**: OpenLDAP bug report https://bugs.openldap.org/show_bug.cgi?id=10431 — both the libFuzzer harness `fuzz_ldif.c` and the direct C driver `test_ldif.c` are pasted in the report.
- **URL fragment**: https://bugs.openldap.org/show_bug.cgi?id=10431
- **Found in**: bug_body (Bugzilla report)
- **Notes**: Fetched via WebFetch. libFuzzer harness calls `ldif_open_mem` + up to 100 `ldif_read_record` iterations. The direct driver opens a file named `poc` for one-shot replay.
