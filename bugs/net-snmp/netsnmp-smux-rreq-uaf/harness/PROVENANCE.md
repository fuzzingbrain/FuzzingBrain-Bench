# netsnmp-smux-rreq-uaf harness provenance

- **Source**: AGF (AI-Guided Fuzzing, O2Lab) LLM-generated libFuzzer harness
  `snmp_agent_e2e_fuzzer.c`, copied verbatim from the vuln-mgmt record
  `projects/iot-targets/net-snmp/heap-use-after-free-smux_rreq_process-via-smux_process/`.
- **Upstream report**: https://github.com/net-snmp/net-snmp/issues/1098
- **Found in**: AGF fuzz run net-snmp-genonly_20260528 (REPORT.md), harness LG
  "SMUX_peer_PDU_processing".
- **Notes**: The harness authorizes a SMUX peer
  (`smux_parse_peer_auth("smuxpeer", "1.3.6.1.4.1.8072 ")`), opens a loopback
  TCP listener, sends a well-formed SMUX_OPEN PDU, calls `smux_accept()` (the
  genuine peer-registration entry point), then wraps one fuzz-controlled SMUX
  PDU (type byte + BER length + body) and calls `smux_process()` (the genuine
  per-packet entry point). It references internal smux_* symbols via `extern`,
  so the agent must be built with the smux mibgroup. `init_agent`/`init_snmp`
  run once in LLVMFuzzerInitialize.
- **PoC**: `poc/poc.bin` is the 75-byte AGF-discovered crash input
  (crash hash 0ac98df6), a sequence of SMUX RReq (0x62) PDUs over OID
  1.3.6.1.4.1.8072 with alternating priority bytes that drive the
  register/unregister churn freeing then re-touching the subtree handler.
  This same input was confirmed in a LIVE unmodified snmpd daemon over TCP
  (VERIFY.md / asan_real_snmpd.txt), so it is not a harness artifact.
