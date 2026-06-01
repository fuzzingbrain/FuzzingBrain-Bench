# Provenance — icu-translit-rule-dtor-uaf

- **Upstream report:** https://unicode-org.atlassian.net/browse/ICU-23365 (Jira)
- **Fixed version:** ICU 79.1 (fixed 2026-04-17).
- **vuln_commit:** `8be6575f5c4ea397d384493a435b2932d5c2eaca` (2026-04-07) — bug PRESENT
  (predates the ICU-23365 fix). Same source revision used by the sibling icu bundle.
- **CVE:** none. Severity high. Discovered/submitted 2026-04-09, confirmed/fixed 2026-04-17.
- **Discovery:** O2 Security Team (FuzzingBrain).
- **Origin record:** `O2_Vulnerability_Management/projects/icu/uaf-TransliterationRule-destructor/`

## Distinct from the sibling icu bundle

This is **not** `icu-translit-rule-uaf` (that bundle is a *leak* in
`TransliteratorIDParser::parseFilterID`). This bug is a use-after-free / invalid free in
`TransliterationRule::~TransliterationRule()` (rbt_rule.cpp). Both are reachable through
`Transliterator::createFromRules`, but they are different root causes and different sites.
Confirmed **not** in `O2/FP/icu` (which lists only the two StringMatcher stack-overflows and
the TransliteratorParser leak).

## Root cause

`TransliteratorParser::parseRule()` fails partway through constructing a
`TransliterationRule`; the destructor calls `delete` on `anteContext` (rbt_rule.cpp:196)
which is uninitialized or dangling. The constructor uses raw `clone()` calls without
null-checking, so on partial construction the destructor frees garbage pointers.

## Harness

`translit_uaf_fuzzer.cpp` — libFuzzer driver over the public
`Transliterator::createFromRules()` API (first byte = direction, rest = UTF-16 rule string).
Public-API path, not a hand-built invalid state — passes the FP screen. Oracle site/class
are keyed to this bundle's actual ASan output at the pinned vuln_commit.
