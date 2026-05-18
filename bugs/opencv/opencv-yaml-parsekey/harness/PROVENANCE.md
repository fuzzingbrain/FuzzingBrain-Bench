# opencv-yaml-parsekey harness provenance

- **Source**: Issue body of https://github.com/opencv/opencv/issues/28619 — section "Steps to reproduce" provides a small C++ driver (`poc.cpp`). The issue also notes that the bug was discovered by fixing OSS-Fuzz harness `filestorage_read_file_fuzzer.cc` (via google/oss-fuzz#15092) which previously had `storage.open()` commented out.
- **URL fragment**: https://github.com/opencv/opencv/issues/28619#issue
- **Found in**: issue_body (small C++ repro driver) + linked oss-fuzz PR (refers to upstream harness)
- **Notes**: bench-corpus.json best-guess was `filestorage_read_string_fuzzer.cc`; the issue confirms the actual upstream OSS-Fuzz harness is `filestorage_read_file_fuzzer.cc` (the file path harness). The reporter's C++ driver written here is what the issue itself provides.
