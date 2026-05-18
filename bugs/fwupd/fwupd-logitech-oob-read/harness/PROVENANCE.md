# fwupd-logitech-oob-read harness provenance

- **Source**: PR #9791 (linked from issue body of #9792 — "If you check out #9791 you can reproduce with a single command").
- **URL fragment**: https://github.com/fwupd/fwupd/pull/9791 files `fuzzing/protocol_fuzzer.c` and `build_and_repro.sh`
- **Found in**: linked PR (referenced from issue_body)
- **Notes**: libFuzzer harness `fuzzing/protocol_fuzzer.c` wraps `fu_logitech_bulkcontroller_device_sync_wait_any_fuzz()`. A `__wrap_fu_usb_device_bulk_transfer` shim feeds the input through the production parser. Auxiliary `build_and_repro.sh` automates oss-fuzz + ASAN build. Fetched from PR head sha 6a9e389fa5e52478c5bf01ec0acee269fc321dd4.
