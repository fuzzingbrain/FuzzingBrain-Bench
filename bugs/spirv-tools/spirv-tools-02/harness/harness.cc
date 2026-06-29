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
