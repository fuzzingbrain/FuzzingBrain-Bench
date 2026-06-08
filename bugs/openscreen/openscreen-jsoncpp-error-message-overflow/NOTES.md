# Notes — openscreen-jsoncpp-error-message-overflow

## Source record
`projects/chromium/openscreen-hbo-jsoncpp-getFormattedErrorMessages-cr-byte-overread/`.
The record stores the openscreen RECEIVER-message harness
(`openscreen_receiver_message_json_parse_fuzzer.cc`) as the discovering
harness; it is kept verbatim in `harness/`.

## Class
Genuine **heap-buffer-overflow READ** (1 byte, off-by-one past the input
buffer end), CWE-125 — matches the task brief. The faulting library frame is
jsoncpp's `Json::OurReader::getLocationLineAndColumn` at
`src/lib_json/json_reader.cpp:1828` (the CR-LF look-ahead `if (*current ==
'\n')`). Confirmed in the record's `prod_repro.log`
("heap-buffer-overflow ... READ of size 1 ... 0 bytes after 1-byte region").

## vuln_commit
jsoncpp `42e892d96e47b1f6e29844cc705e148ec4856448` from the repro
`method.yaml` (`commit_sha`/`library_repo_url`). The bug is in jsoncpp itself,
so `target.repo` is jsoncpp upstream (not openscreen).

## Build feasibility
The verbatim openscreen harness is a Chromium GN libFuzzer target and cannot
be built standalone. The Dockerfile/`build.sh` reproduce the SAME jsoncpp
library frame via the discovery **Path-B** repro
(`repro_jsoncpp_cr_oob.cc`): jsoncpp built statically at the vendored SHA with
production defines (`-DNDEBUG -DJSON_USE_EXCEPTION=0 -fno-exceptions`) linked
to a public-API program that uses the identical
`Json::CharReader::parse(begin, end, &root, &errs)` call shape as
`openscreen::json::Parse`. `release-asan` uses `-O1` (not `-O2`) to keep the
unambiguous `getLocationLineAndColumn` top frame; at `-O2` that loop inlines
and the top frame symbolizes as `getFormattedErrorMessages` (same :1828
source line). Not compiled/validated here (task: no docker/compile).

## PoC
`poc/poc.bin` is the canonical 1-byte PoC from the repro `generate_poc.py`:
a single CR (`0x0d`). (The raw record crash file `crash-69aad888...` was
`[[[[...[\r[[[\r`, an unminimized libFuzzer input ending in CR; the 1-byte CR
is the reduced trigger the repro uses.)
