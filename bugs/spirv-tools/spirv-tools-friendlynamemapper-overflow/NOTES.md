# Notes — spirv-tools-friendlynamemapper-overflow

## Source record
`projects/chromium/hbo-spirv-tools-FriendlyNameMapper-ParseInstruction-OpTypePointer/`
plus repro bundle
`data/chrome/libraries/spirv-tools/harnesses/spirv_dis_extended_options/.repro/`.

## Class
**heap-buffer-overflow READ** (4 bytes), CWE-125 / CWE-129 — matches the task
brief. Faulting library frame: `FriendlyNameMapper::ParseInstruction` at
`source/name_mapper.cpp:268:47` ("READ of size 4 ... 0 bytes after 32-byte
region"). Full capability set. Same vuln_commit as the existing
`spirv-orderblocks-segv` entry but a DIFFERENT bug (different file/function,
different option bit, HBO-read vs SEGV-write).

## vuln_commit
`ff5c50339cc1e9f34f04cb440a3e5fe89db0161d` from the repro `method.yaml`
(`commit_sha`) and `build.sh`.

## Build feasibility
**Standalone-buildable.** Unlike the openscreen/printing entries, this harness
(`spirv_dis_extended_options_fuzzer.cc`) is a self-contained libFuzzer harness
that uses only the SPIRV-Tools public C API (`spvBinaryToText`) plus
`<fuzzer/FuzzedDataProvider.h>` (clang fuzzer runtime). `build.sh` mirrors the
existing `spirv-orderblocks-segv` bundle: cmake build of `SPIRV-Tools-static`
with ASan (deps fetched via `utils/git-sync-deps`), then links the harness with
`-fsanitize=fuzzer,address`. Not compiled here (task: no docker/compile), but
the build is faithful to the discovery setup.

## PoC
`poc/poc.bin` is the verbatim 35-byte original libFuzzer crash input from the
source record (`crash-731164ad5b65f4770c63c264368682163f`); `generate_poc.py`
rematerializes it byte-for-byte. Because THIS bench builds the libFuzzer
harness (`spirv_dis_extended_options_fuzzer.cc`), the harness wire format is
required: FuzzedDataProvider reads 3 option bytes from the END of the buffer
(here `0x78 0xff 0x7f` -> legacy 0x78 = FRIENDLY_NAMES, extended 0xff =
HANDLE_UNKNOWN_OPCODES) and the leading 32 bytes (8 words) are the SPIR-V
stream carrying the short-encoded OpTypePointer.

The repro bundle's separate 32-byte `generate_poc.py` output
(`...0x20,0x00,0x03,0x00, ... 0x2a,0x00,0x00,0x00`) is the FDP-stripped pure
word stream that the public-API Path-B `repro.cc` consumes — NOT what the
libFuzzer harness in this bundle takes. We use the 35-byte harness-wire form so
poc.bin matches the harness this Dockerfile builds.
