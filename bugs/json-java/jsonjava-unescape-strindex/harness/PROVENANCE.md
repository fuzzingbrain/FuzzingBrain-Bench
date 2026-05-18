# jsonjava-unescape-strindex harness provenance

- **Source**: Issue body of https://github.com/stleary/JSON-java/issues/1035 — section "Trigger Method 2: Fuzzer (Jazzer)".
- **URL fragment**: https://github.com/stleary/JSON-java/issues/1035#issue
- **Found in**: issue_body
- **Notes**: Jazzer harness `XmlToJsonFuzzer.java` calls `XML.toJSONObject(input)`; only catches `JSONException` so `StringIndexOutOfBoundsException` propagates to crash the fuzzer.
