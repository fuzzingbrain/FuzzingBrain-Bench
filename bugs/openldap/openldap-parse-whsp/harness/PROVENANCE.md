# openldap-parse-whsp harness provenance

- **Source**: OpenLDAP bug report https://bugs.openldap.org/show_bug.cgi?id=10430 — both the libFuzzer harness `fuzz_schema.c` and a direct C driver are pasted in the report.
- **URL fragment**: https://bugs.openldap.org/show_bug.cgi?id=10430
- **Found in**: bug_body (Bugzilla report)
- **Notes**: Fetched via WebFetch. libFuzzer harness exercises both `ldap_str2attributetype` and `ldap_str2objectclass` across all 5 `LDAP_SCHEMA_ALLOW_*` flag combinations. PoC trigger input is a malformed schema string ending mid-token.
