# libaom-restore-layer-overflow — off-target ablation note

**bug_id:** libaom-restore-layer-overflow
**verdict: inseparable-same-defect** (outcome B — the off-target is NOT a distinct
defect from the preset; it is a magnitude-variant of the same OOB)

## Summary
The catalogued "off-target" SEGV and the preset heap-buffer-overflow are the **same
defect**: an out-of-bounds WRITE into `cpi_->svc.layer_context[layer]` driven by an
unvalidated, attacker-controlled `spatial_layer_id`. They differ only in the *magnitude*
of the OOB index (a function of `number_temporal_layers`), which changes which frame
ASan happens to trip on. No surgical guard can remove one without removing the other,
because both flow from the identical bad index; the only lever that stops the off-target
(bounding `spatial_layer_id`) is exactly the upstream fix that also closes the preset.

## Shared root cause (decoded from both PoCs)
Both PoCs use the harness pattern: an initial config with `ss_number_layers = 4`, then a
`UpdateRateControl(new_cfg)` that shrinks `number_spatial_layers` to **1** (and reallocs
`layer_context` to `ss*ts` entries). The harness then clamps `frame_params.spatial_layer_id`
to the **original** count, feeding `spatial_layer_id = 3` while the live
`number_spatial_layers = 1`. `ComputeQP` stores it unchecked and computes
`layer = LAYER_IDS_TO_IDX(spatial_id, temporal_id, number_temporal_layers)
       = 3 * number_temporal_layers + temporal_id`, indexing past the allocated array.

| PoC        | live ss | live ts | alloc entries | layer index | OOB by | ASan class |
|------------|---------|---------|---------------|-------------|--------|------------|
| preset     | 1       | 4       | 4             | **12**      | 8      | heap-buffer-overflow |
| off-target | 1       | 8       | 8             | **24**      | 16     | SEGV |

`is_key_frame` and `max_mv_magnitude` are the **last** fields of `LAYER_CONTEXT`;
`rc.avg_frame_bandwidth` is at offset ~0. With layer=24 the high-offset field crosses
onto an unmapped page → SEGV inside `ComputeQP`. With layer=12 that same high-offset
write stays mapped, so the crash instead surfaces one frame later on the low-offset
`rc.avg_frame_bandwidth` write inside `av1_update_temporal_layer_framerate` → ASan
redzone → heap-buffer-overflow. Same array, same bad index, different field/page.

## Evidence — both PoCs on OLD V1 (release-asan benchmark binary)

### off-target PoC → SEGV in ComputeQP
```
==ERROR: AddressSanitizer: SEGV on unknown address 0x6330000535d0
The signal is caused by a WRITE memory access.
  #0 aom::AV1RateControlRTC::ComputeQP(...) av1/ratectrl_rtc.cc      <- layer_context[24].is_key_frame = 1  (line 324)
  #1 LLVMFuzzerTestOneInput libaom_ratectrl_rtc_interface_fuzzer.cc:172
```

### preset PoC → heap-buffer-overflow
```
==ERROR: AddressSanitizer: heap-buffer-overflow on address 0x7f457fec467c
WRITE of size 4 at 0x7f457fec467c
  #0 av1_update_temporal_layer_framerate av1/encoder/svc_layercontext.c:192  <- lrc->avg_frame_bandwidth (layer_context[12])
  #1 aom::AV1RateControlRTC::ComputeQP(...) av1/ratectrl_rtc.cc:339
  #2 LLVMFuzzerTestOneInput libaom_ratectrl_rtc_interface_fuzzer.cc:172
allocated by thread T0 here:
  ... aom_calloc av1/encoder/svc_layercontext.c  <- av1_alloc_layer_context, the layer_context[] array
```
Both are WRITE OOB accesses into the `layer_context[]` array allocated by
`av1_alloc_layer_context`. Same allocation, same indexing bug.

## Why no surgical guard separates them (empirical)
A minimal, principled bounds guard was placed at the **off-target frame only** — the two
`cpi_->svc.layer_context[layer].is_key_frame = …` writes in `ComputeQP` — skipping the
write when `layer` is outside `number_spatial_layers * number_temporal_layers`. It leaves
the preset's crash site (`av1_update_temporal_layer_framerate`) untouched. Patch:
`tools/offtarget/patches/libaom-restore-layer-overflow.patch`.

Build + verify (`build_and_verify.py`, new V1 = vuln+patch, new V2 = fix+patch):
```
P1_offtarget_removed:        false   <- off-target STILL faults on new V1
P2_preset_intact:            true    <- preset heap-bof still fires (guard didn't touch it)
P3_v2_no_preset_fault:       true
CTRL_old_v1_faults_offtarget:true
VERDICT: FAIL
```
new V1 on the off-target PoC — the SEGV simply **relocated** to the next OOB access on the
**same** `layer_context[24]` struct:
```
AddressSanitizer: SEGV on unknown address 0x633000053570   (old V1 faulted at 0x6330000535d0 — same struct, ~0x60 apart)
site: /src/aom/av1/ratectrl_rtc.cc:343   (av1_update_temporal_layer_framerate / av1_restore_layer_context on layer 24)
```
Because every `layer_context[layer]` access in `ComputeQP` → `av1_update_temporal_layer_framerate`
→ `av1_restore_layer_context` uses the same out-of-range `layer = 24`, suppressing one
access only exposes the next. `av1_restore_layer_context` additionally reads
`lc->max_mv_magnitude` (the last field of `LAYER_CONTEXT`, same unmapped tail as
`is_key_frame`), guaranteeing a downstream fault.

The only lever that stops the off-target is bounding `spatial_layer_id` against the live
`number_spatial_layers` — which is exactly the upstream fix
(`40b50c6f556df8df4e9876ffcdf842fbfd0d25b4`, the early `return kFrameDropDecisionDrop`
guard at the top of `ComputeQP`). P3 confirms that fix closes the **preset**. Therefore
any guard that removes the off-target also removes the preset → P2 would fail.

## Conclusion
This off-target SEGV is a duplicate/magnitude-variant of the preset heap-buffer-overflow,
not a distinct interfering defect. (The original O2 finding's VERIFY.md already flagged it
as a "probable variant/duplicate"; this analysis proves it.) It should be treated as
**no distinct off-target** for the ablation — i.e. an effectively interference-free /
null-control bundle — rather than rebuilt with a confounded patch that weakens the preset.

The patch at `tools/offtarget/patches/libaom-restore-layer-overflow.patch` is retained only
as the negative-control evidence above (it is principled and preserves P2/P3, but cannot
satisfy P1). Do NOT promote it as a New V1.
