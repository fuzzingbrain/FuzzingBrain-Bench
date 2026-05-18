# avro-neg-block-size harness provenance

- **Source**: First comment by reporter on https://github.com/apache/avro/pull/3623
- **URL fragment**: https://github.com/apache/avro/pull/3623#issuecomment-3746385334
- **Found in**: comment_3746385334
- **Notes**: libFuzzer harness `datafile_fuzzer.c` exercises `avro_file_reader_fp()` / `avro_file_reader_read_value()` by writing input to a temp file and reading up to 100 values.
