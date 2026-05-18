# netsnmp-vacm-parse-npd harness provenance

- **Source**: Issue body of https://github.com/net-snmp/net-snmp/issues/1052 — section "Trigger Method 2: Fuzzer (libFuzzer)".
- **URL fragment**: https://github.com/net-snmp/net-snmp/issues/1052#issue
- **Found in**: issue_body
- **Notes**: libFuzzer harness `vacm_fuzzer.c` directly calls `vacm_parse_config_group("vacmGroup", line)` with the fuzz input null-terminated as the line argument. Initializes `init_snmp("vacm_fuzzer")` once at startup.
