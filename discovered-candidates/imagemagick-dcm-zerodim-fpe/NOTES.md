# Deferred candidate — imagemagick DCM invalid-dimensions divide-by-zero (CVE-2026-49218)

**Status: deferred (no reproducing PoC yet).** Not added to `bugs/` because it does not yet
have a deterministic, oracle-verified reproduction. Documented here per the workflow's
"discovered-candidates" rule so it can be finished.

## What it is
- **CVE-2026-49218** / **GHSA-8pj9-6897-74xc** (High, CVSS 7.5). "Policy Bypass in DCM decoder
  could result in image with invalid dimensions" → downstream division-by-zero crash.
- **Fixed in:** ImageMagick 7.1.2-24 / 6.9.13-48.
- **Fix commit:** `84fbcef8a558` (2026-05-22) — "Added missing check for returning an image with
  zero columns". Diff adds, in `ReadDCMImage` (coders/dcm.c, ~line 4376, after the decode loop):
  ```c
  if ((image->rows == 0) || (image->columns == 0))
    ThrowReaderException(CorruptImageError,"ImproperImageHeader")
  ```
- **vuln_commit (parent of fix):** `4ac379a7c43ddeba92c859a8607cd72f205054eb` — at this commit
  `ReadDCMImage` can RETURN an image with 0 rows/columns; a later operation that divides by the
  dimension then crashes (FPE / div-by-zero per the advisory).

## Why it isn't reproduced yet (the blocker)
The DCM reader ALREADY guards the obvious case inside its per-element loop:
`coders/dcm.c:3897  if ((info.width == 0) || (info.height == 0)) ThrowDCMException(...)`.
So a DICOM that simply sets Columns (0028,0011)=0 is rejected there. The end-of-function check
the fix adds (at ~4376) implies a *different* path leaves `image->columns==0` after the loop
(e.g. multi-frame / image-list handling around the `group==0xfffc`/`group==0x0000` break at
dcm.c:3886, or a scene/list path at dcm.c:4116). Producing that state needs a crafted multi-element
DICOM, and there is **no reference PoC** in the O2 records (only the advisory text).

## What's needed to finish
1. `git checkout 4ac379a7` ImageMagick; build a DCM-reading libFuzzer harness (reuse the
   ImageMagick autoconf build from `bugs/imagemagick/imagemagick-kernelinfo-alloc/harness/build.sh`).
2. Harness: `ReadImage` the DCM bytes, then invoke an op that does integer `%`/`/` by
   `image->columns`/`image->rows` (e.g. `RollImage`) to turn the 0-dim image into a SIGFPE — OR
   confirm which downstream op the advisory means.
3. Craft a DICOM that reaches the post-loop 0-column state (study the dcm.c:3886 list-break and
   dcm.c:4116 scene path). Verify ReadDCMImage returns columns==0 at 4ac379a7 and the op FPEs.
4. Oracle: class `segv`/FPE (SIGFPE) — note: a plain integer div-by-zero raises SIGFPE; the oracle's
   crashFired matches SIGFPE. capability_set likely `[reach, crash, site]` (no sanitizer class token
   for a raw FPE).

No `bugs/` bundle was created so `fb-bench list` / `grade-all` stay clean.
