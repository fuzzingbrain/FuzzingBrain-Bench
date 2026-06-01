# Provenance — libvpx-vp9-reconfig-overflow

- **Upstream report:** https://issues.webmproject.org/issues/501696590 (webm bugtracker)
- **vuln_commit:** `a5e2e6528374c8ae7cfe8ef6b7aad4fc327c8688` (libvpx main, 2026-04-09) — bug PRESENT
  (discovered against libvpx main 2026-04-11).
- **Status note:** the chrome submissions dashboard records this as `fixed`; the O2 project
  tracker records it as `confirmed` (date_confirmed 2026-04-14, webm bugtracker). Listed because
  it was triaged as fixed in the chrome arm; the status sources disagree, recorded here for honesty.
- **CVE:** none. Severity high.
- **Discovery:** O2 Security Team (FuzzingBrain), chrome libvpx arm.
- **Origin record:** `O2_Vulnerability_Management/projects/libvpx/heap-overflow-vp9-encoder-midstream-reconfig/`
  + `data/chrome/libraries/libvpx/harnesses/vp9_encoder_midstream_reconfig/`.

## Root cause

VP9 encoder allocates `prev_mi` / `lf_mask` context buffers from the initial dimensions.
`vpx_codec_enc_config_set` -> `vp9_change_config` re-runs dimension math but does not reallocate
these when new dimensions exceed the initial allocation; a later encode writes past the buffer in
`init_encode_frame_mb_context` (vp9/encoder/vp9_encodeframe.c) — heap-buffer-overflow.

## Harness (FP screen)

`vp9_encoder_midstream_reconfig_fuzzer.cc` drives the public encoder API
(vpx_codec_enc_config_default -> enc_init -> loop of config_set + encode) — a legitimate caller
pattern (mid-stream reconfiguration is a documented use of vpx_codec_enc_config_set). Not a
hand-built invalid internal state — passes the FP screen. Oracle keyed to this bundle's actual output.
