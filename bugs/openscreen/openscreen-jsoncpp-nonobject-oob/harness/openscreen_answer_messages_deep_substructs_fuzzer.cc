#ifdef UNSAFE_BUFFERS_BUILD
#pragma allow_unsafe_buffers
#endif
// Copyright 2019 The Chromium Authors
// Use of this source code is governed by a BSD-style license that can be
// found in the LICENSE file.

// libFuzzer harness for Logic Group: openscreen_answer_messages_deep_substructs
//
// Target: the public `static ErrorOr<T> TryParse(const Json::Value&)`
// entries on each sub-struct of a Cast ANSWER message:
//
//   - openscreen::cast::AudioConstraints::TryParse
//   - openscreen::cast::VideoConstraints::TryParse
//   - openscreen::cast::Constraints::TryParse
//   - openscreen::cast::AspectRatio::TryParse
//   - openscreen::cast::DisplayDescription::TryParse
//
// Rationale: ReceiverMessage::Parse → Answer::TryParse short-circuits on
// the first missing sibling, so deep sub-struct arithmetic (SimpleFraction,
// Dimensions, max_pixels_per_second double, aspect-ratio N:M parser) often
// never runs on malformed input when fuzzed through the top-level path.
// Directly invoking each sub-struct's public static TryParse means every
// mutation actually lands inside that sub-struct's parser body.
//
// Coverage goals:
//   - Per-field arithmetic: SimpleFraction::FromString (num/den integer
//     parse + division), Dimensions::TryParse (width*height downstream),
//     max_pixels_per_second double parse (NaN/Inf propagation).
//   - Vector / list walks.
//   - Optional<T> field population.
//
// The first byte of the fuzz input selects which sub-struct to parse;
// the rest is treated as JSON text. This keeps per-entry coverage
// attribution clean in libFuzzer.

#include <cstddef>
#include <cstdint>
#include <string>
#include <string_view>

#include "cast/streaming/public/answer_messages.h"
#include "json/value.h"
#include "platform/base/error.h"
#include "util/json/json_serialization.h"

namespace {

// Picks one of the five public sub-struct TryParse entries and runs it
// on the given Json::Value. Return value is ignored.
void DispatchOne(uint8_t selector, const Json::Value& v) {
  switch (selector % 5u) {
    case 0:
      (void)openscreen::cast::AudioConstraints::TryParse(v);
      return;
    case 1:
      (void)openscreen::cast::VideoConstraints::TryParse(v);
      return;
    case 2:
      (void)openscreen::cast::Constraints::TryParse(v);
      return;
    case 3:
      (void)openscreen::cast::AspectRatio::TryParse(v);
      return;
    case 4:
      (void)openscreen::cast::DisplayDescription::TryParse(v);
      return;
  }
}

}  // namespace

extern "C" int LLVMFuzzerTestOneInput(const uint8_t* data, size_t size) {
  if (size == 0) {
    return 0;
  }
  const uint8_t selector = data[0];
  std::string_view as_text(reinterpret_cast<const char*>(data + 1), size - 1);

  openscreen::ErrorOr<Json::Value> json_or =
      openscreen::json::Parse(as_text);
  if (json_or.is_error()) {
    return 0;
  }

  DispatchOne(selector, json_or.value());
  return 0;
}
