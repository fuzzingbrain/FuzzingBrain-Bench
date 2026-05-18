# simdutf-utf16-utf8-overflow harness provenance

- **Source**: Issue body of https://github.com/simdutf/simdutf/issues/911 — sections "Minimal reproduction" (`poc.cpp`) and "Fuzzer harness" (`fuzz_find_safe.cpp`). The reporter notes "This is a custom fuzzer we wrote to test `_safe()` functions not covered by existing fuzzers".
- **URL fragment**: https://github.com/simdutf/simdutf/issues/911#issue
- **Found in**: issue_body
- **Notes**: libFuzzer harness `fuzz_find_safe.cpp` dispatches between several `_safe` functions; the case relevant here is `fuzz_convert_utf16_to_utf8_safe`. Also includes the small `poc.cpp` driver.
