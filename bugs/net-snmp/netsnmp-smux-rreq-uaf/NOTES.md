# NOTES — netsnmp-smux-rreq-uaf

## Provenance
- Faithfully authored from vuln-mgmt record
  `projects/iot-targets/net-snmp/heap-use-after-free-smux_rreq_process-via-smux_process/`
  (vuln.yaml, VERIFY.md, REPORT.md, asan_real_snmpd.txt).
- Harness `snmp_agent_e2e_fuzzer.c` and `poc/poc.bin` (75-byte crash_input)
  copied **verbatim** from the record.
- Class: **heap-use-after-free** -> sanitizer asan, full caps
  `[reach, crash, class, site]`.
- Upstream: https://github.com/net-snmp/net-snmp/issues/1098 (fixed 2026-05-31,
  maintainer hardaker; no CVE — root/admin auth-required service).

## Gaps / things to validate (no compile performed, per instructions)
1. **vuln_commit is a SHORT SHA (`1852fec16`).** The record only captured the
   short master SHA ("present on master (1852fec16, 2026-05-27)"); the full
   40-char SHA was not recorded. Resolve to the full SHA before pinning the
   Dockerfile build. The DELETE-path region is noted as unchanged since 2012,
   so most recent master commits reproduce.
2. **Build differs from netsnmp-vacm-parse-npd.** That entry builds only
   `snmplib` with `--disable-agent`. This harness needs the **agent + smux
   mibgroup** and links internal `smux_*` symbols, so `build.sh` was adapted to
   configure with `--with-mib-modules=smux` and `make` the full agent tree,
   then link against `libnetsnmpagent.a` + `libnetsnmpmibs.a` + `libnetsnmp.a`.
   The exact `.a` names/paths and the set of libs required to resolve the
   `extern` smux_* symbols have NOT been verified by an actual build — confirm
   against the configured tree (net-snmp may also emit `libnetsnmphelpers.a`).
3. **Grader site line (agent_handler.c:350).** Taken from the ASan top frame in
   the live-daemon trace. Line numbers can drift with the resolved full SHA;
   `line_tolerance: 5` provides slack but re-check after pinning the commit.
4. **No `binaries/` directory** is included (NO binaries per task). The bench
   harness must be built from the Dockerfile.
