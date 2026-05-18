# avro-neg-string-len harness provenance

- **Source**: First comment by reporter on https://github.com/apache/avro/pull/3622
- **URL fragment**: https://github.com/apache/avro/pull/3622#issuecomment-3746521711
- **Found in**: comment_3746521711
- **Notes**: libFuzzer harness `value_reader_fuzzer.c` exercises `avro_value_read()` across a table of 20 predefined schemas (the first input byte selects schema).
