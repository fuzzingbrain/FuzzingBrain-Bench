// Copyright (c) 2026 Google Inc.
//
// Licensed under the Apache License, Version 2.0 (the "License");
// you may not use this file except in compliance with the License.
// You may obtain a copy of the License at
//
//     http://www.apache.org/licenses/LICENSE-2.0
//
// Unless required by applicable law or agreed to in writing, software
// distributed under the License is distributed on an "AS IS" BASIS,
// WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
// See the License for the specific language governing permissions and
// limitations under the License.

// libFuzzer harness for Logic Group: spirv_dis_extended_options
//
// Drives spvBinaryToText (C API) with the FOUR newer disassembler option
// bits that the in-tree spvtools_dis_fuzzer.cpp does NOT exercise:
//     SPV_BINARY_TO_TEXT_OPTION_COMMENT             (bit 7)
//     SPV_BINARY_TO_TEXT_OPTION_NESTED_INDENT       (bit 8)
//     SPV_BINARY_TO_TEXT_OPTION_REORDER_BLOCKS      (bit 9)
//     SPV_BINARY_TO_TEXT_OPTION_HANDLE_UNKNOWN_OPCODES (bit 10)
// The existing dis_fuzzer loops options from 0..0x7E (bits 0..6 only),
// so bits 7..10 are cold code at fuzz time even though each of them
// enables a non-trivial new emission path inside the disassembler:
//   - COMMENT adds annotation logic walking OpDecorate chains.
//   - NESTED_INDENT tracks structured-control-flow nesting state.
//   - REORDER_BLOCKS runs a secondary CFG traversal before printing.
//   - HANDLE_UNKNOWN_OPCODES changes the opcode-dispatch fallback.
// All four bits are combinable, so the harness fuzz-selects any subset
// (16 combos) from a single header byte AND also drives the older bits
// 0..6 via another byte so the full option-space is covered.
//
// Input layout (FuzzedDataProvider):
//   byte 0   : low nibble = target_env selector (see PickEnv).
//   byte 1   : extended option bits (bits 0..3 -> COMMENT / NESTED_INDENT
//              / REORDER_BLOCKS / HANDLE_UNKNOWN_OPCODES).
//   byte 2   : legacy option bits (bits 0..6 -> NONE / PRINT / COLOR /
//              INDENT / SHOW_BYTE_OFFSET / NO_HEADER / FRIENDLY_NAMES).
//              bit 7 forces the legacy byte to zero when set (so the
//              extended-bits-only case is exercised distinctly).
//   bytes 3..: SPIR-V word stream (4-byte LE aligned).

#include <cstddef>
#include <cstdint>
#include <cstring>
#include <vector>

#include <fuzzer/FuzzedDataProvider.h>

#include "spirv-tools/libspirv.h"

namespace {

constexpr size_t kMaxWords = 16 * 1024;  // 64KB input cap.

spv_target_env PickEnv(uint8_t nibble) {
  switch (nibble & 0x0F) {
    case 0:  return SPV_ENV_UNIVERSAL_1_0;
    case 1:  return SPV_ENV_UNIVERSAL_1_1;
    case 2:  return SPV_ENV_UNIVERSAL_1_2;
    case 3:  return SPV_ENV_UNIVERSAL_1_3;
    case 4:  return SPV_ENV_UNIVERSAL_1_4;
    case 5:  return SPV_ENV_UNIVERSAL_1_5;
    case 6:  return SPV_ENV_VULKAN_1_0;
    case 7:  return SPV_ENV_VULKAN_1_1;
    case 8:  return SPV_ENV_VULKAN_1_2;
    case 9:  return SPV_ENV_VULKAN_1_3;
    case 10: return SPV_ENV_OPENGL_4_5;
    case 11: return SPV_ENV_OPENCL_1_2;
    default: return SPV_ENV_UNIVERSAL_1_5;
  }
}

}  // namespace

extern "C" int LLVMFuzzerTestOneInput(const uint8_t* data, size_t size) {
  // 3-byte header + at least a 1-word SPIR-V body (the dis APIs bail
  // on size < 4 anyway, we pre-filter to keep libFuzzer focused).
  if (size < 3 + sizeof(uint32_t)) {
    return 0;
  }

  FuzzedDataProvider fdp(data, size);
  const uint8_t env_byte       = fdp.ConsumeIntegral<uint8_t>();
  const uint8_t extended_byte  = fdp.ConsumeIntegral<uint8_t>();
  const uint8_t legacy_byte    = fdp.ConsumeIntegral<uint8_t>();

  const spv_target_env env = PickEnv(env_byte);

  uint32_t options = 0;
  if (extended_byte & 0x01u) options |= SPV_BINARY_TO_TEXT_OPTION_COMMENT;
  if (extended_byte & 0x02u) options |= SPV_BINARY_TO_TEXT_OPTION_NESTED_INDENT;
  if (extended_byte & 0x04u) options |= SPV_BINARY_TO_TEXT_OPTION_REORDER_BLOCKS;
  if (extended_byte & 0x08u) {
    options |= SPV_BINARY_TO_TEXT_OPTION_HANDLE_UNKNOWN_OPCODES;
  }

  // Suppress the PRINT bit — PRINT writes to stdout from inside the
  // library which adds noise to the fuzz log and has no bug-finding
  // value for this LG.
  if ((legacy_byte & 0x80u) == 0) {
    if (legacy_byte & 0x01u) options |= SPV_BINARY_TO_TEXT_OPTION_NONE;
    if (legacy_byte & 0x04u) options |= SPV_BINARY_TO_TEXT_OPTION_COLOR;
    if (legacy_byte & 0x08u) options |= SPV_BINARY_TO_TEXT_OPTION_INDENT;
    if (legacy_byte & 0x10u) {
      options |= SPV_BINARY_TO_TEXT_OPTION_SHOW_BYTE_OFFSET;
    }
    if (legacy_byte & 0x20u) options |= SPV_BINARY_TO_TEXT_OPTION_NO_HEADER;
    if (legacy_byte & 0x40u) options |= SPV_BINARY_TO_TEXT_OPTION_FRIENDLY_NAMES;
  }

  const std::vector<uint8_t> body = fdp.ConsumeRemainingBytes<uint8_t>();
  if (body.size() < sizeof(uint32_t)) return 0;

  const size_t word_count = std::min(body.size() / sizeof(uint32_t), kMaxWords);
  std::vector<uint32_t> binary(word_count);
  // LE byte-to-word pack. memcpy is safe because word_count is derived
  // from body.size() via floor-div and the multiply cannot overflow for
  // the 64KB cap.
  if (word_count > 0) {
    std::memcpy(binary.data(), body.data(), word_count * sizeof(uint32_t));
  }

  const spv_context context = spvContextCreate(env);
  if (context == nullptr) return 0;

  spv_text text = nullptr;
  spv_diagnostic diagnostic = nullptr;

  (void)spvBinaryToText(context, binary.data(), binary.size(), options, &text,
                        &diagnostic);

  if (diagnostic != nullptr) {
    spvDiagnosticDestroy(diagnostic);
    diagnostic = nullptr;
  }
  if (text != nullptr) {
    spvTextDestroy(text);
    text = nullptr;
  }

  spvContextDestroy(context);
  return 0;
}
