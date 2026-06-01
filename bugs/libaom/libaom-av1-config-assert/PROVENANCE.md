# Provenance — libaom-av1-config-assert

- **Class:** reachable assertion `assert(bits <= 31)` (aom_dsp/bitreader_buffer.c:40, aom_rb_read_literal)
  reached from `parse_timing_info` -> `parse_sequence_header` -> `get_av1config_from_obu` (common/av1_config.c).
- **Status:** fixed (chrome submissions dashboard `fixed`; CVSS 3.1 6.5 medium).
- **vuln_commit:** `f23c9437a` (April 2026 libaom main) — assertion PRESENT.
- **Discovery:** O2 / FuzzingBrain chrome libaom arm.
- **Origin record:** `data/chrome/libraries/libaom/harnesses/av1_config/` +
  `data/chrome/bug_reports/libaom/assert-failure-aom-rb-read-literal.md`.

## capability_set note

`capability_set: [reach, crash, site]` — class omitted (plain C assert->abort, no sanitizer token).
crash on SIGABRT; libFuzzer prints a symbolized stack -> reach + site. **Built with asserts ON**
(Debug, no -DNDEBUG): the assertion is the documented crash. `common/av1_config.c` is compiled
directly into the harness (it is not part of libaom.a in this minimal config).

## Harness (FP screen)

`av1_config_fuzzer.cc` drives the public AV1 config-box parsers (get_av1config_from_obu /
read_av1config) on attacker bytes — the path browsers/players use for AV1-in-MP4/WebM. Passes the FP screen.
