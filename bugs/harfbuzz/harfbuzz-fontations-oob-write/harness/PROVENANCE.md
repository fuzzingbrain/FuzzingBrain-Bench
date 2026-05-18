# harfbuzz-fontations-oob-write harness provenance

- **Source**: Issue body of https://github.com/harfbuzz/harfbuzz/issues/5946 — section "Reproduction steps" shows a small C driver (not a libFuzzer harness).
- **URL fragment**: https://github.com/harfbuzz/harfbuzz/issues/5946#issue
- **Found in**: issue_body
- **Notes**: The reporter provides a 12-line C `main()` calling `hb_font_get_glyph_name(font, 0, buf, 0)` against an attacker-controlled font file. **No libFuzzer/AFL harness is attached**. The report says the issue was discovered via "internal security audit" (line-by-line data-flow trace), not by an existing fuzzer. `oss_fuzz.notes` in bench-corpus.json claims `hb-shape-fuzzer.cc` is the likely OSS-Fuzz reach harness, but the specific size==0 condition is not naturally reached by that harness (the issue says "The C wrapper hb_font_t::get_glyph_name() does not normalize size == 0 before dispatch, so the underflow is reachable from public API" — i.e. requires a caller explicitly passing size=0). The PoC above is the reporter's only harness.
