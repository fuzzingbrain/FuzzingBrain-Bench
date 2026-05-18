# graaljs-illformed-locale harness provenance

- **Source**: Issue body of https://github.com/oracle/graaljs/issues/985 — section "Trigger Method 2: Fuzzer (Jazzer)".
- **URL fragment**: https://github.com/oracle/graaljs/issues/985#issue
- **Found in**: issue_body
- **Notes**: Jazzer harness `IntlFuzzer.java` constructs a polyglot `Context`, consumes the fuzz input as a string, escapes it, and evaluates `new Intl.Locale(...)`. It throws a `RuntimeException` when a `PolyglotException` is classified as internal (the bug condition).
