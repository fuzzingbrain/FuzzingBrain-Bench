# graal-regexlexer-oob harness provenance

- **Source**: Issue body of https://github.com/oracle/graaljs/issues/986 — section "Trigger Method 2: Fuzzer (Jazzer)". The harness's `escapeForJS` body was elided in the report (`/* same as above */`) referring to the snippet earlier in the same issue body — reproduced here.
- **URL fragment**: https://github.com/oracle/graaljs/issues/986#issue
- **Found in**: issue_body
- **Notes**: Jazzer harness `RegExpFuzzer.java` exercises `new RegExp(pattern, 'v' or '')` and flags an internal `PolyglotException` as the bug condition.
