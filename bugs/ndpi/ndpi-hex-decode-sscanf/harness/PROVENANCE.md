# ndpi-hex-decode-sscanf harness provenance

- **Source**: Issue body of https://github.com/ntop/nDPI/issues/3159 names the harness `fuzz_ndpi_decode_tls_blocks` and describes its behavior ("one-shot: it takes the fuzzer-supplied buffer and calls `ndpi_decode_tls_blocks(buf, len, out, &out_len)`"). The actual source was added by the reporter in PR #3163 (linked in comments) at `fuzz/fuzz_ndpi_decode_tls_blocks.c`.
- **URL fragment**: https://github.com/ntop/nDPI/pull/3163 file `fuzz/fuzz_ndpi_decode_tls_blocks.c`
- **Found in**: linked PR (referenced from comments)
- **Notes**: Fetched from PR head sha. The harness is small (~34 lines).
