#ifdef UNSAFE_BUFFERS_BUILD
#pragma allow_unsafe_buffers
#endif
// Copyright 2020 The Chromium Authors
// Use of this source code is governed by a BSD-style license that can be
// found in the LICENSE file.

// libFuzzer harness for Logic Group: openscreen_receiver_message_json_parse
//
// Target: openscreen::cast::ReceiverMessage::Parse as invoked by
//         openscreen::cast::SenderSessionMessenger::OnMessage.
//
// Threat model: a Chrome sender session receives JSON reply bytes from a
// Cast receiver that is attacker-controlled (any rogue device on the LAN
// that a webpage's Presentation API request connects to). The real code
// path is:
//
//     ReceiverMessage::Parse(json::Parse(message_string))
//
// which is what SenderSessionMessenger::OnMessage does after the
// source_id/namespace checks. We reproduce the same two-call sequence
// here so the fuzzer sees exactly the parse pipeline a rogue receiver
// can reach.
//
// Coverage goals:
//   - ReceiverMessage::Parse dispatch on "type" ∈ {ANSWER,
//     CAPABILITIES_RESPONSE, RPC, INPUT} and the unknown-type fallthrough.
//   - Answer::TryParse + nested Constraints / DisplayDescription /
//     AspectRatio / AudioConstraints / VideoConstraints.
//   - ReceiverCapability::Parse and ReceiverError::Parse.
//   - base64 body decode for RPC/INPUT variants (large attacker-sized
//     vector<uint8_t> allocation).

#include <cstddef>
#include <cstdint>
#include <string>
#include <string_view>

#include "cast/streaming/public/receiver_message.h"
#include "json/value.h"
#include "platform/base/error.h"
#include "util/json/json_serialization.h"

extern "C" int LLVMFuzzerTestOneInput(const uint8_t* data, size_t size) {
  // jsoncpp caps extremely-large inputs on its own, but libFuzzer likes
  // very short mutations; we treat the whole buffer as the JSON string.
  // Empty input is valid (json::Parse will return an error, we just
  // return 0).
  std::string_view as_text(reinterpret_cast<const char*>(data), size);

  openscreen::ErrorOr<Json::Value> json_or =
      openscreen::json::Parse(as_text);
  if (json_or.is_error()) {
    // Exactly what SenderSessionMessenger::OnMessage does on bad JSON.
    return 0;
  }

  // Exercise the full ReceiverMessage::Parse dispatcher on the parsed
  // Json::Value. The result (Answer / Capability / Error / RPC vector)

  // inside the parser, not about the return value.
  openscreen::ErrorOr<openscreen::cast::ReceiverMessage> parsed =
      openscreen::cast::ReceiverMessage::Parse(json_or.value());

  // Force the variant body to be touched so LTO / O1 can't optimise the
  // parser body away. A released-mode dead-code-eliminator may otherwise
  // see ReceiverMessage::body as unused.
  if (parsed.is_value()) {
    const auto& m = parsed.value();
    (void)m.type;
    (void)m.sequence_number;
    (void)m.valid;
    // Index touches the variant discriminator; this is O(1), no copies.
    (void)m.body.index();
  }

  return 0;
}
