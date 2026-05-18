# jsonjava-unescape-numformat harness provenance

- **Source**: Issue body of https://github.com/stleary/JSON-java/issues/1036 — section "Trigger Method 2: Fuzzer (Jazzer)".
- **URL fragment**: https://github.com/stleary/JSON-java/issues/1036#issue
- **Found in**: issue_body
- **Notes**: Same Jazzer harness `XmlToJsonFuzzer.java` as jsonjava-unescape-strindex (both bugs sit in `XMLTokener.unescapeEntity`). Only catches `JSONException`; `NumberFormatException` propagates.
