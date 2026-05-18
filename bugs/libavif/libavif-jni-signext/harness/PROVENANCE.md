# libavif-jni-signext harness provenance

- **Source**: Issue body of https://github.com/AOMediaCodec/libavif/issues/3177 — section "Exact reproduction steps" / "Android/JNI surface".
- **URL fragment**: https://github.com/AOMediaCodec/libavif/issues/3177#issue
- **Found in**: issue_body (partial — only a Java reproducer snippet; no libFuzzer harness source code)
- **Notes**: The report shows a small Java JNI reproducer (saved as `repro.java`) calling `AvifDecoder.getInfo(buf, -1, info)`. A separate native-boundary replay binary `tr1_neg_length_parse` is mentioned as having been used during confirmation, but **its source is NOT pasted in the report**. The harness needs human verification to retrieve the native-side driver source if it is desired.
