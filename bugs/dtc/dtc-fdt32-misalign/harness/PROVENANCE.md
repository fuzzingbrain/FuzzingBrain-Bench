# dtc-fdt32-misalign harness provenance

- **Source**: Issue body of https://github.com/dgibson/dtc/issues/178 (section "Trigger Method 2: Fuzzer (libFuzzer)").
- **URL fragment**: https://github.com/dgibson/dtc/issues/178#issue-body
- **Found in**: issue_body
- **Notes**: libFuzzer harness `fuzz_fdt.c` exercises `fdt_check_header()` then traverses the FDT with `fdt_for_each_subnode` / `fdt_for_each_property_offset` to trigger the misaligned access in `fdt_next_tag()`.
