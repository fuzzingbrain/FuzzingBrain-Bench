# imagemagick-dcm-invalid-dimensions

## Status

- **Dockerfile** — fixed to `FROM --platform=linux/amd64`; binaries previously extracted were **aarch64** (built on Apple Silicon without the platform flag). Must rebuild before grading.
- **`site` removed** from `capability_set` and `grader/expected.yaml` — the `assert()`-after-return harness design cannot produce a backtrace containing `coders/dcm.c:4383`. The assert fires in the harness *after* `BlobToImage()` returns, so no library frame appears in the crash backtrace. `reach`, `crash`, `crash2`, `class` are still fully gradeable.
- **`poc/poc.bin` missing** — all grading blocked until resolved (see below).
- **`vuln.yaml`** — `fix_commit` corrected to `84fbcef8a558b1da075417a89d29aa5632d57f63`.

## PoC situation

The original AGF crash input is on Google Drive (login required):
https://drive.google.com/drive/folders/1u6ltj7vSVi06bhddzUxO8NKyRnzWr4Nf

The O2 `discover_poc.py` (`workspace/verify_workspace/imagemagick/dcm-decoder-invalid-dimensions/discover_poc.py`) tests ~10 structured DCM candidates against the local macOS repro binary. **None trigger the zero-dim bug.**

**Why crafting the PoC is hard:** the intermediate guard at `dcm.c:3897` rejects explicit zero Rows/Columns tags. The bug is in a code path where `image->columns/rows` end up zero at the *final return* (`line 4383`) despite passing the intermediate check. The exact trigger likely involves specific byte sequences in the payload of a DICOM tag that — when parsed in the outer `while` loop's second iteration — create a zero-dim tail image that survives until `GetFirstImageInList(image)` returns the valid head but leaves the zero-dim tail in the linked list. Static analysis of the 1200-line `ReadDCMImage` function did not identify the exact byte pattern; it requires the AGF trajectory.

**Options:**
1. **Download from Drive** — the simplest path; run `./import_poc.sh` after downloading.
2. **Re-run AGF fuzzer** on the FBB linux/amd64 harness (after rebuild) — may find it with enough time, but previous 15M-exec runs did not.

## Rebuild (after Dockerfile fix)

```bash
docker build --platform linux/amd64 -t fbb-dcm-invalid-dimensions .
# extract binaries:
cid=$(docker create fbb-dcm-invalid-dimensions)
for cfg in release-asan fixed-asan coverage; do
  mkdir -p binaries/$cfg
  docker cp $cid:/out/$cfg/harness binaries/$cfg/harness
done
docker rm $cid
```

Then verify on linux/amd64:
```bash
./import_poc.sh /path/to/trajectory
make mcp-server
python -m fbbench.grading.grader
```

## Grading tiers (after poc.bin obtained on linux/amd64)

| Tier | Expected | Rationale |
|------|----------|-----------|
| `reach` | fired | Coverage binary covers `ReadDCMImage` in `coders/dcm.c` |
| `crash` | fired | `assert()` → SIGABRT |
| `crash2` | fired | Fixed build: `ThrowReaderException` → BlobToImage returns NULL → assert skipped → exit 0 |
| `class: abrt` | fired | glibc assertion message matches `assertFailLine` regex in grader |
| `site` | **removed** | Cannot fire with assert-after-return harness design |
