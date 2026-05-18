# freerdp-ntlm-memleak harness provenance

- **Source**: PR #12610 (referenced from the last comment on issue #12603).
- **URL fragment**: https://github.com/FreeRDP/FreeRDP/pull/12610 file `winpr/libwinpr/sspi/test/TestFuzzNTLMMessage.c`
- **Found in**: linked PR (referenced from comment on issue_body)
- **Notes**: The issue body names the harness `TestFuzzNTLMMessage` and notes the 1-byte dispatch selector to route between NTLM message parsers; the actual source was added in PR #12610 by the same reporter. File fetched from raw PR head sha c3c724726668e2ce112c2e4c638891aef78345a8.
