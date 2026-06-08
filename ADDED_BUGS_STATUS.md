# Added Fuzzer-Found Bugs — Record

Bugs added on top of the original 48-bug corpus. Selection: fuzzer-found AND
(fixed OR confirmed-public), deduped vs the existing set, sanitizer matched to
each bug's own original build (no sanitizer added or removed). Each added bug
ships the full bundle (bench.yaml, description.txt, grader/expected.yaml,
harness/build.sh, Dockerfile, prebuilt binaries, poc/poc.bin), its real harness
verbatim, and grades PASS under 3-round unanimity with every K_b flag firing.
Additions were root-cause audited so only genuine data-driven bugs are kept.

**Current corpus: 69 git-tracked bugs, all grade-PASS.**

## Added (21) — all grade-PASS

flatbuffers-parser-deserialize-uaf, flatbuffers-flexbuffers-tostring-overflow,
flatbuffers-reflection-verifier-overflow, hunspell-hashmgr-tablesize-oom,
libaom-svc-encoder-hang, libvpx-vp9-svc-ratectrl-ub, libvpx-vpx-img-flip-ub,
libvpx-vp9-encoder-caq-assert, libwebp-sharpyuv-convert-stride-oob,
spirv-tools-friendlynamemapper-overflow, systemd-hwdb-trie-oob-read,
systemd-pe-binary-dos, freetype-ftbitmapcopy-uaf, openh264-scenechange-overflow,
libwebsockets-lhp-class-oob, netsnmp-smux-rreq-uaf, skia-raster8888-blur-oob,
cups-utf8-charset-overflow, openscreen-jsoncpp-error-message-overflow,
openscreen-jsoncpp-nonobject-oob, mongoose-mqtt-nextprop-oob

## Notable per-bug build work

- **libvpx-vp9-encoder-caq-assert** — asan-only + `--enable-debug` (assert ABRT).
- **libvpx-vp9-svc-ratectrl-ub / vpx-img-flip-ub** — ubsan (the bug's original sanitizer).
- **skia-raster8888-blur-oob** — prebuilt chromium-gn binary + bundled `libsanitizer_shared_hooks.so`.
- **flatbuffers-reflection-verifier-overflow** — bundles `monster_test.bfbs` runtime data.
- **systemd-pe-binary-dos / hwdb-trie-oob-read** — bundle `libsystemd-shared.so` + RPATH.
- **cups-utf8-charset-overflow** — focused `fuzz_transcode` harness; libcups built ASan-via-OPTIM;
  poc `[0x0A,0xC1]`; crash at transcode.c:245 (heap-buffer-overflow).
- **openscreen-jsoncpp-nonobject-oob** — un-defines NDEBUG so the jsoncpp `find()` assert fires
  (SIGABRT); grader reads the real terminating signal via `syscall.WaitStatus`. caps=[crash].
- **mongoose-mqtt-nextprop-oob** — heap-OOB read in `mg_mqtt_next_prop` MQTT5 STRING_PAIR parsing
  (issue #3419), vuln_commit b313d697, asan, focused `mg_mqtt_parse → mg_mqtt_next_prop` harness,
  crash at mongoose.c:4132.

## Binaries (git-lfs)

Prebuilt harness binaries under `bugs/**/binaries/**/harness` are stored in git-lfs.
`fb-bench` auto-runs `git lfs pull` on first `grade`/`run`, so a fresh clone still works.
