# Notes — openscreen-jsoncpp-nonobject-oob

## Merge
This single entry merges three source records that share one root cause and
one fix class (jsoncpp `Value::find` precondition abort reached by indexing a
non-object `Json::Value` with a string key, fixed by an `isObject()` guard):

- `dos-openscreen-answer-messages-jsoncpp-non-object-find` (**primary** — its
  harness + crash are used here; ANSWER sub-struct parsers,
  answer_messages.cc, tracker 505902443)
- `dos-openscreen-receiver-message-jsoncpp-non-object-find` (receiver_message.cc,
  tracker 505902444)
- `dos-openscreen-sender-message-jsoncpp-non-object-find` (sender_message.cc,
  tracker 505947418)

## Bug class discrepancy (IMPORTANT)
The task brief labeled this "heap-buffer-overflow read (asan)". The actual,
verified crash is **not** a heap-buffer-overflow. Every trace in the source
record (harness ASan output and the Path-B `prod_repro.log`) is a **deadly
signal / ABRT** — a reachable assertion: jsoncpp's `JSON_ASSERT_MESSAGE`
inside `Json::Value::find` fails and runs `abort()` (CWE-617 / CWE-754). The
grader (`class: abrt`) and description reflect the real evidence, not the
brief's label. (The genuinely heap-buffer-overflow-read jsoncpp bug in this
batch is the separate entry `openscreen-jsoncpp-error-message-overflow`.)

## vuln_commit
`adca75ad5d978fde166d18efedee039e36394c8f` (openscreen) from the answer-messages
repro `method.yaml` (`commit_sha`). The crashing code is in bundled jsoncpp;
openscreen pins jsoncpp **1.9.4** (`method.yaml: jsoncpp_version`), so the
Dockerfile builds jsoncpp at tag 1.9.4.

## Build feasibility
The verbatim harness `openscreen_answer_messages_deep_substructs_fuzzer.cc`
is a Chromium GN libFuzzer target (depends on `//cast/streaming`,
`openscreen::json::Parse`, `//third_party/jsoncpp`) and **cannot be built
standalone** outside a full openscreen/chromium `gn`+`ninja` checkout. It is
kept verbatim in `harness/` for provenance.

The Dockerfile/`build.sh` reproduce the SAME top library frame
(`Json::Value::find`, json_value.cpp) via the discovery **Path-B** repro:
jsoncpp 1.9.4 built statically with openscreen's production defines
(`-DNDEBUG -DJSON_USE_EXCEPTION=0 -fno-exceptions`) linked to
`repro_jsoncpp_array_string_index.cc`, which uses the identical
`const Json::Value&; v[key]` call shape. The repro's `prod_repro.log`
confirms `#5 Json::Value::find json_value.cpp:1082` under those flags.
This Path-B build was NOT compiled/validated here (task: no docker/compile).

## PoC
`poc/poc.bin` is the canonical 5-byte PoC from the repro `generate_poc.py`
(`\x00[]\x00\x05`): selector byte 0 -> AudioConstraints::TryParse, payload
`[]` parses to arrayValue. (The raw record crash file
`crash-0b9712306177...` was `[[]\n\n\n`, the unminimized libFuzzer input;
both reach the same abort.)
