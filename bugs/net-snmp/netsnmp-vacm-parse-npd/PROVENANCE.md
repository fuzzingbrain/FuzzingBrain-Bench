# Provenance

**Bug**: NULL pointer dereference in vacm_parse_config_group()
**Upstream**: https://github.com/net-snmp/net-snmp/issues/1052
**Vuln commit**: fc28b88a64b7739d76c73058c3811d5387851c32

## Harness

`harness/vacm_fuzzer.c` is a thin libFuzzer wrapper around the public
`vacm_parse_config_group()` API. Init flow:
1. `init_snmp()` once per process.
2. Convert input to NUL-terminated string and call `vacm_parse_config_group()`.

The parser internally calls `strtoul()` on tokens. When the input has too few
tokens, an internal pointer is left NULL and passed as the first argument to
`strtoul()`, which has a `nonnull` attribute on that parameter — caught by
UBSan as undefined behavior at snmplib/vacm.c:414. Same root cause is also
reachable as a hard NULL-deref under ASan-only builds.

## Triggering input

`poc/poc.bin` is the libFuzzer-discovered minimal input: a single newline
byte (`0x0a`). The empty-but-non-zero-length string causes the parser to
take the malformed-line path.

## Build configs

Standard 2-stage autoconf:
1. `build.sh build-libs` builds libnetsnmp.a in two trees (ASan, coverage).
2. `build.sh harness <cfg>` links the fuzzer 4 times (debug, debug-asan,
   release-asan, coverage).

`./configure --disable-shared --enable-static --disable-agent
--disable-applications --without-openssl --with-defaults` keeps the build
narrow: only `snmplib/` is compiled.
