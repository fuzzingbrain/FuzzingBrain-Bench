# Off-target interference ablation — plan & status

**Branch:** `feat/offtarget-ablation`  ·  **Started:** 2026-06-23

## Research question
Does interference from OTHER bugs (off-target crashes reachable in the same harness)
degrade an agent's performance at finding the **preset** bug? Off-target removal is the
experiment's independent variable — not cleanup.

## Two binary sets (both kept; current binaries = Arm A, never deleted)
- **Old V1** = current vuln binary: preset bug + off-target interference present (Arm A).
- **Old V2** = current `fixed-asan`: preset also patched (crash2 oracle for old V1).
- **New V1** = vuln binary with the off-target(s) suppressed (interference-free, Arm B).
  Built ONLY for bugs that have a catalogued off-target.
- **New V2** = new V1 + `fix_commit`/`fix_patch` (preset also patched) = crash2 oracle for new V1.

Build mechanism: `delta-bisect/bin/build_at.py <bug> <commit> --patch <p> --config release-asan`
(supports applying a unified diff to the source at a pinned commit). New V1 = vuln_commit+patch,
New V2 = fix_commit+patch.

## Source of off-targets — ALREADY CATALOGUED
`/data4/ze/O2_Vulnerability_Management/incoming_report/offtarget-*` (23 verified reports,
3 batches: 2026-06-02 full-scan, 06-04 diff-0, 06-12 full-v1). Each has `repro.yaml`/`vuln.yaml`
(preset class, off-target class+top_frame, sanitizer, benchmark vuln_commit), a PoC, and a backtrace.
This REPLACES re-grading 3116 PoCs — the inventory is given.

## Inventory: 23 off-targets → 19 distinct bundles  (tools/offtarget/inventory.json)

Buckets by removal mechanism:

| bucket | n | mechanism | confound risk |
|---|---|---|---|
| suppressable-ubsan | 5 | `__attribute__((no_sanitize("undefined")))` on off-target fn, or UBSAN suppressions file | none (logic identical) |
| suppressable-leak | 2 | LSan suppressions file (runtime), no recompile | none |
| memcorruption-sourcefix | 5 | apply the OTHER bug's upstream fix (real source change) | control-flow change — document |
| oom-artifact | 6 | raise rss_limit / -Xmx, or confirm it never fires under grade env | likely harness artifact, may be no-op |
| stack-exhaustion | 2 | recursion depth guard / stack limit | medium |
| java-exception | 2 | catch/neutralize the uncaught exception in source | medium |
| assert-abort | 1 | disable the specific assert | low |

### Per-bundle mapping
| bundle | off-target entry | bucket |
|---|---|---|
| avro/avro-neg-string-len | avro-array_items, avro-generic_value_new, avro-schema_name | suppressable-ubsan ×3 |
| dtc/dtc-fdt32-misalign | dtc-fdt32-misalign-ubsan | suppressable-ubsan |
| flatbuffers/flatbuffers-flexbuffers-tostring-overflow | flexbuffers-tostring-stack-overflow | stack-exhaustion |
| flatbuffers/flatbuffers-parser-deserialize-uaf | parser-deserialize-uaf-segv | memcorruption-sourcefix |
| fwupd/fwupd-logitech-oob-read | logitech-protocol-oom | oom-artifact |
| graaljs/graaljs-illformed-locale | escapeForJS-oom | oom-artifact |
| harfbuzz/harfbuzz-fontations-oob-write | hb_calloc-leak | suppressable-leak |
| icu/icu-translit-rule-uaf | rulehalf-parse-leak | suppressable-leak |
| jq/jq-dump-op-npd | dump-op-npd-oom | oom-artifact |
| libaom/libaom-restore-layer-overflow | restore-layer-overflow-segv | memcorruption-sourcefix |
| libavif/libavif-jni-signext | avifROStreamRead-segv | memcorruption-sourcefix |
| mongoose/mongoose-mg-match-overflow | mg_match-stack-overflow | stack-exhaustion |
| ndpi/ndpi-hex-decode-sscanf | hex-decode-sscanf-oom | oom-artifact |
| net-snmp/netsnmp-smux-rreq-uaf | smux-rreq-uaf-heap-buffer-overflow | memcorruption-sourcefix |
| pdfbox/pdfbox-cmap-bfrange-aioob | cmap-bfrange-aioob-classcast, cmap-codespacerange-exception | java-exception ×2 |
| spirv-tools/spirv-orderblocks-segv | orderblocks-abort | assert-abort |
| spirv-tools/spirv-tools-friendlynamemapper-overflow | friendlynamemapper-overflow-oom | oom-artifact |
| systemd/systemd-pe-binary-dos | pe-binary-dos-oom | oom-artifact |
| upx/upx-elf32-pack2-memleak | calls_crt1-null-deref, elf32-pack2-memleak-segv | suppressable-ubsan + memcorruption |

The 68−19 = **49 bundles have NO catalogued off-target → untouched (reuse old V1/V2), serve as null control.**

## Verified interference (tools/offtarget/interference_verified.json, grader env)
Ran every off-target PoC on its mapped bundle's existing release-asan binary:
- **15 offtarget-confirmed** (crash fires, preset K_b NOT satisfied = real interference)
- **7 no-crash** (PoC does not fault on the benchmark binary under grade env)
- **1 solves-preset** (systemd-pe — misfiled; the PoC IS the preset → DROP)

### To-rebuild set (confirmed interference) — 13 bundles
dtc-fdt32-misalign · flatbuffers-flexbuffers-tostring-overflow · flatbuffers-parser-deserialize-uaf ·
fwupd-logitech-oob-read · icu-translit-rule-uaf · libaom-restore-layer-overflow · libavif-jni-signext ·
mongoose-mg-match-overflow · netsnmp-smux-rreq-uaf · pdfbox-cmap-bfrange-aioob (×2 off-targets) ·
spirv-orderblocks-segv · spirv-tools-friendlynamemapper-overflow · upx-elf32-pack2-memleak (×2)

### Excluded — verified NON-interfering on the benchmark binary (NOT a skip; the IV is absent)
- **avro ×3** (array_items, generic_value_new, schema_name): the avro `release-asan` build is
  `-fsanitize=fuzzer,address` — **no UBSan**. These off-targets fire ONLY under `-fsanitize=undefined
  -fno-sanitize-recover` (a separate 06-02 experiment build), so they physically cannot fault on this
  benchmark binary nor for the agent (same binary). Empirically confirmed no-crash.
- **systemd-pe-binary-dos**: PoC solves the preset (class+crash+crash2+reach) → misfiled, dropped.
- **OOM artifacts pending agent-env check** (graaljs, jq, ndpi escaped grade env as no-crash; fwupd &
  spirv-friendlyname fired): OOM = libFuzzer rss_limit / Java -Xmx resource exhaustion, not a distinct
  defect. Handled in a separate tier — kept only if they genuinely fire for the agent.

## Status (live)
- [x] Step 1 — inventory (23 off-targets from incoming_report) → inventory.json
- [x] Step 2 — bucket + map to 19 bundles + self-verify interference → 13 confirmed to-rebuild
- [~] Step 3/4/5/6 — per-bug authored patch → build new V1+V2 → verify, all driven by
  `tools/offtarget/build_and_verify.py <bug> --patch <p>` (idempotent; writes results/<bug>.json).
  Verdict PASS iff: P1 new-V1 no-fault on off-target · P2 new-V1 faults on preset · P3 new-V2
  no-fault on preset · CTRL old-V1 faults on off-target.
  - **PASS & staged (11/13):** dtc, flatbuffers-flexbuffers-tostring-overflow, flatbuffers-parser-deserialize-uaf,
    libavif-jni-signext, mongoose-mg-match-overflow, spirv-orderblocks-segv, spirv-tools-friendlynamemapper-overflow,
    netsnmp-smux-rreq-uaf, fwupd-logitech-oob-read, upx-elf32-pack2-memleak, pdfbox-cmap-bfrange-aioob
  - **libaom-restore-layer-overflow: INSEPARABLE-SAME-DEFECT** (NOTE.md) — the off-target SEGV and the preset
    heap-bof are the same OOB layer_context[] write (unvalidated spatial_layer_id), differing only by OOB
    magnitude (layer 12 vs 24). No surgical guard separates them; only the upstream fix (which also closes the
    preset) stops it. → NOT a distinct off-target; reclassified as a null-control bundle. A real finding: the
    ablation method DETECTED a catalogued variant/duplicate (O2 VERIFY.md had already flagged it "probable variant").
  - in-flight: icu-translit-rule-uaf (last build)
- [x] Two-arm grade() differential VALIDATED on dtc (Arm A off-target fires crash; Arm B fires only reach; preset full set both arms)
- [~] Step 6 — `tools/offtarget/stage_armB.py` → bugs-armB/ (source symlinked, release-asan=new V1)
- [~] Step 7 — `tools/offtarget/run_two_arm.py` (runner gained `--oracle-dir` for Arm B); runs only the
  rebuilt bugs (others null-identical). delta = solved/turns (Arm A − Arm B).

## Proven recipe (per bucket)
- **ubsan** (dtc done): `__attribute__((no_sanitize("<check>")))` on the off-target function,
  scoped to the off-target's UBSan CHECK TYPE only (e.g. signed-integer-overflow) so the preset's
  different UBSan check (e.g. alignment) keeps firing. Build via build_at.py --patch. Logic identical.
- **leak**: `no_sanitize` won't stop a leak; free the leaked alloc OR (cleanest) the off-target
  leak only fires with detect_leaks=1 — if the bundle's preset is non-leak, the grader gates
  detect_leaks=0 so the off-target is already invisible (verify under grade env first).
- **memcorruption (segv/uaf/heap-bof)**: NOT sanitizer-suppressible — apply the OTHER bug's upstream
  fix or a minimal guard at the off-target site so the input no longer corrupts memory. Confound:
  control-flow change; document it.
- **stack-exhaustion / assert / java-exception / oom**: per-bug; see results/.

## Step 7 mechanism (validated by reading the runner/MCP server)
The agent NEVER runs the harness binary itself: `exec` runs in the sandbox view (binaries withheld,
oracle dir tmpfs-masked). It observes crashes ONLY via `grade()`, which runs `oracle_dir/binaries/
release-asan/harness` server-side. So the off-target suppression lives ONLY in the oracle binary and is
**invisible to the agent** — a clean independent variable, no source leak.
- Runner resolves `oracle_dir = find_bug(--bug, repo_root)` and stages the source view from the same dir.
- **Arm A** = normal `bugs/` tree (old V1 oracle).
- **Arm B** = a parallel `bugs-armB/<proj>/<bug>/` tree (source identical; `binaries/release-asan/harness`
  = new V1; `binaries/fixed-asan/harness` = old V2 or new V2). Run the sweep with repo_root → Arm-B tree
  (or add a `--oracle-dir` override to the runner). Only the ~13 rebuilt bugs differ between arms; the
  other ~56 are byte-identical → null control (no need to spend agent budget on them).
- delta = solve-rate / turns-to-preset (Arm A) − (Arm B), per bug, same model+seed.

## FINAL build results (steps 1–6 complete)
**12/13 to-rebuild bugs PASS** (off-target removed, preset intact, verified through grade()):
dtc, flatbuffers-flexbuffers-tostring-overflow, flatbuffers-parser-deserialize-uaf, libavif-jni-signext,
mongoose-mg-match-overflow, spirv-orderblocks-segv, spirv-tools-friendlynamemapper-overflow,
netsnmp-smux-rreq-uaf, fwupd-logitech-oob-read, upx-elf32-pack2-memleak, pdfbox-cmap-bfrange-aioob,
icu-translit-rule-uaf. All staged to bugs-armB/.
**1/13 = libaom-restore-layer-overflow: inseparable-same-defect** (not a distinct off-target → null control).
Mechanisms spanned every bucket: scoped UBSan no_sanitize, scoped LSan suppression, recursion guards,
assert→graceful-return, bounds/null guards (upstream fixes), allocation-size caps for OOM.

## Step 7 — RUNNING (tracked bg task)
`run_two_arm.py --models claude-haiku-4-5 --seeds 0,1 --max-turns 120` over the 12 rebuilt bugs ×
{Arm A = old V1 oracle, Arm B = new V1 oracle}. Default mode (no force-full) so off-target-induced early
stops / wasted turns are measurable. Output: runs/offtarget-eval/{armA,armB}/.../score.json +
two_arm_results.json. delta = solved/turns (Arm A − Arm B). Resumable; can extend seeds/models.

## Mandate
No-skip / no-stop (user 2026-06-23). Only "zero off-target → don't rebuild" is allowed
(designed null control). Claims scope to OBSERVED off-targets, never "all".
