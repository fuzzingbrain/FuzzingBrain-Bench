#include <spirv-tools/libspirv.h>

#include <cstdint>
#include <cstddef>
#include <cstring>
#include <vector>

extern "C" int LLVMFuzzerTestOneInput(const uint8_t* data, size_t size) {
  // SPIR-V is a stream of 32-bit words; need at least one word.
  if (size < 4 || (size % 4) != 0) return 0;

  std::vector<uint32_t> words(size / 4);
  std::memcpy(words.data(), data, size);

  spv_context ctx = spvContextCreate(SPV_ENV_UNIVERSAL_1_6);
  if (!ctx) return 0;

  spv_text text = nullptr;
  spv_diagnostic diag = nullptr;
  const uint32_t opts = SPV_BINARY_TO_TEXT_OPTION_FRIENDLY_NAMES |
                        SPV_BINARY_TO_TEXT_OPTION_REORDER_BLOCKS;
  spvBinaryToText(ctx, words.data(), words.size(), opts, &text, &diag);

  if (diag) spvDiagnosticDestroy(diag);
  if (text) spvTextDestroy(text);
  spvContextDestroy(ctx);
  return 0;
}
