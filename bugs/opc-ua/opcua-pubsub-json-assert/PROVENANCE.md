# Provenance — opcua-pubsub-json-assert

- **Upstream fix:** https://github.com/open62541/open62541/pull/7680 (merged 2026-01-28).
- **vuln_commit:** `0b75ea2c5a78e72dc3c04302be7ec3546a556958` (PR #7680 base) — bug PRESENT (pre-fix).
- **CVE:** none. Severity medium. Reported via open62541-security@googlegroups.com,
  confirmed/fixed 2026-01-28. Affected v1.4 / v1.5-rc.
- **Discovery:** O2 Security Team (FuzzingBrain).
- **Origin record:** `O2_Vulnerability_Management/projects/iot-targets/opc-ua/Assertion-Failure-JSON-Decode/`
- Listed **Fixed #4** in `O2/projects/VULNERABILITIES.md`.

## Root cause

In the PubSub JSON NetworkMessage decoder, `lookAheadForKey()` asserts
`currentTokenType(ctx) == CJ5_TOKEN_OBJECT`. Malformed JSON whose top-level value is an
array (e.g. `[]`) makes the current token an array, so the assertion fails and the process
aborts (SIGABRT). Reachable through the public `UA_NetworkMessage_decodeJson` on
attacker-supplied bytes.

## capability_set note

`capability_set: [reach, crash, site]` — **class is omitted**: this is a plain C `assert()`
abort with no sanitizer SUMMARY, so the oracle has no class token for it. crash fires on the
SIGABRT; libFuzzer prints a symbolized backtrace, giving reach + site at the decoder frame.

## Harness (FP screen)

`fuzz_pubsub_json.cc` — the upstream-style fuzzer over the public
`UA_NetworkMessage_decodeJson` API; last 4 bytes set a memory limit (open62541 fuzz
convention). Linked with the in-tree `tests/fuzz/custom_memory_manager.c`. Public-API path,
not a hand-built invalid state — passes the FP screen. Oracle site keyed to the actual build.
