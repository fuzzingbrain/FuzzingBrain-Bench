# Provenance

**Bug**: Memory leak of NTLM context allocation pre-auth
**Upstream**: https://github.com/FreeRDP/FreeRDP/issues/12603
**Vuln commit**: d0418739c27fe95b0d38fc6aa2e3cb22b7ac1cee

## Harness

`harness/TestFuzzNTLMMessage.c` is from PR #12610 (linked from the
issue). Drives `AcceptSecurityContext()` / `InitializeSecurityContext()`
on a fuzz-provided NTLM token; first byte selects which step
(negotiate / challenge / authenticate).

## Build

FreeRDP is large cmake. We only need libwinpr-sspi, so the Dockerfile
disables X11/Wayland/clients/servers/channels/FFmpeg/audio/etc. and
builds only the `winpr` target. ICU is required by winpr's
unicode_icu module; Debian doesn't ship libicuuc.a, so the binary
links the .so files and we **bundle them in binaries/lib/** (~36 MB).
The link uses `-Wl,-rpath,'$ORIGIN/../lib'` so the harness finds them
without `LD_LIBRARY_PATH`.

## Triggering input

`poc/poc.bin` is 9 bytes (`u-stmllti`). The first byte routes to
`fuzz_ntlm_negotiate`, then the remaining bytes are passed as the
inbound NTLM token. `ntlm_AcceptSecurityContext` calls
`ntlm_ContextNew()` (ntlm.c:244) which allocates 1064 bytes; the
malformed token causes an early-return before the context is freed.
LeakSanitizer reports it at exit.

## K_b

`capability_set: [reach, class, site]` — `crash` excluded per
SPEC §2.3 because LeakSanitizer reports at exit, not at a crashing
site.
