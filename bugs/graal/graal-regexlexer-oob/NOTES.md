# Notes / provenance — graal-regexlexer-oob

**Where the bug lives vs. how it was reported.** This entry was originally
filed against graaljs (upstream report
https://github.com/oracle/graaljs/issues/986, "StringIndexOutOfBoundsException
in RegexLexer.consumeChar causes Internal Error"), but the buggy code is **not
in graaljs** — it is in **graal's Truffle regex engine** (`com.oracle.truffle.regex`,
repo `oracle/graal`), which graaljs depends on. A malformed JS regex flows from
graaljs's JS engine into the shared Truffle regex parser and faults there. The
entry is therefore anchored to its real source:

- `target.repo`        = `https://github.com/oracle/graal`
- `target.vuln_commit` = `vm-24.1.2`
- crash site / root    = `regex/src/com.oracle.truffle.regex/src/com/oracle/truffle/regex/tregex/parser/RegexLexer.java`

**The bug.** `RegexLexer.consumeChar()` reads the next pattern character with no
bounds check:

```java
protected char consumeChar() {
    final char c = pattern.charAt(position);   // position == length() -> StringIndexOutOfBoundsException
    advance();
    return c;
}
```

A crafted regex drives a parse path that calls `consumeChar()` past the end of
the pattern, throwing `StringIndexOutOfBoundsException`; graaljs surfaces it as
an Internal Error instead of a JS `SyntaxError`. Verified present (unpatched) at
`vm-24.1.2`.

**Harness / binary.** The trigger is graaljs's JS-regex fuzzer
(`harness/RegExpFuzzer.java`) — a legitimate path to the shared regex engine
(cf. skia-raster8888-blur-oob, whose skia bug is triggered via a chromium
harness). The prebuilt binary is built via the graaljs toolchain (which bundles
the graal regex engine) and grades PASS unchanged; only the staged **source**
and the provenance label were re-anchored from graaljs to graal so the agent
sees the file that actually contains the bug. `K_b = [crash, class]`.
