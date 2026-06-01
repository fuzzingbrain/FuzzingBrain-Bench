# Provenance — spirv-orderblocks-segv

- **Upstream report:** https://github.com/KhronosGroup/SPIRV-Tools/issues/6663
- **Fix:** PR https://github.com/KhronosGroup/SPIRV-Tools/pull/6676 (merge commit
  af15c1bd0e5ec2c3da9e6439bc262cd73c0d79f4, merged 2026-05-30) — guard
  `if (cfg.blocks.empty()) return post_order;`.
- **CVE:** none.
- **vuln_commit:** `ff5c50339cc1e9f34f04cb440a3e5fe89db0161d` — bug PRESENT.
- **Discovery:** AGF (AI-Guided Fuzzing, Aisle Research). Reporter: Ze. Found 2026-04-25,
  submitted 2026-04-30 (issue #6663), fixed 2026-05-30.
- **Origin record:** `O2_Vulnerability_Management/agf-results/projects/oss-fuzz/spirv-tools/segv-OrderBlocks-disassemble-empty-blocks/`

## Root cause

`spvBinaryToText` with `SPV_BINARY_TO_TEXT_OPTION_REORDER_BLOCKS` (or `NESTED_INDENT`)
defers emission and drives a CFG state machine: each `OpLabel` pushes a `SingleBlock`,
each `OpFunctionEnd` calls `EmitCFG()` → `OrderBlocks()`. The first statement of
`OrderBlocks` does `cfg.blocks[0].nest_level = 0;` (source/disassemble.cpp:416) without
checking `cfg.blocks.empty()`. A module with `OpFunctionEnd` and no preceding `OpLabel`
leaves `blocks` empty → write to `nullptr + 0x50` → SIGSEGV. Reachable through the public
C API on attacker-supplied SPIR-V; 24-byte PoC.

## Harness

`spirv_disasm_fuzzer.cc` — adapted from the public-API repro in the upstream issue (Path B).
Uses only `<spirv-tools/libspirv.h>`: `spvBinaryToText` with REORDER_BLOCKS on the input
words. Public-API path, not a hand-built invalid internal state — passes the FP screen.

## Build note

SPIRV-Tools needs SPIRV-Headers; the Dockerfile fetches it via
`python3 utils/git-sync-deps` at the pinned vuln_commit, then builds the static
`libSPIRV-Tools` and links the harness. The oracle's class token is set from this
bundle's actual ASan output.
