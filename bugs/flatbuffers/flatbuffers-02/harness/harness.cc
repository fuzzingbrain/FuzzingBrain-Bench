#include <cstddef>
#include <cstdint>
#include <string>

#include "flatbuffers/idl.h"
#include "flatbuffers/reflection_generated.h"

static constexpr size_t kMaxInputLength = 32768;

extern "C" int LLVMFuzzerTestOneInput(const uint8_t *data, size_t size) {
  if (size < 8 || size > kMaxInputLength) return 0;

  // First 2 bytes: flags + json_len ratio
  uint8_t flags = data[0];
  uint8_t json_ratio = data[1];
  data += 2;
  size -= 2;

  // Split: bfbs portion and json portion
  size_t json_len = (size * json_ratio) / 256;
  size_t bfbs_len = size - json_len;
  if (bfbs_len < 4) return 0;

  const uint8_t *bfbs_data = data;
  const uint8_t *json_data = data + bfbs_len;

  // Verify the bfbs data as a schema buffer.
  flatbuffers::Verifier verifier(bfbs_data, bfbs_len);
  if (!reflection::VerifySchemaBuffer(verifier)) return 0;

  // Deserialize into a Parser.
  flatbuffers::IDLOptions opts;
  opts.strict_json = (flags & 0x80) != 0;
  opts.skip_unexpected_fields_in_json = (flags & 0x40) != 0;
  opts.allow_non_utf8 = (flags & 0x20) != 0;
  opts.output_default_scalars_in_json = (flags & 0x10) != 0;

  flatbuffers::Parser parser(opts);
  if (!parser.Deserialize(bfbs_data, bfbs_len)) return 0;

  // Re-serialize to exercise the serialize path on deserialized data.
  parser.Serialize();
  auto *buf = parser.builder_.GetBufferPointer();
  auto buf_size = parser.builder_.GetSize();

  flatbuffers::Verifier re_verifier(buf, buf_size);
  if (!reflection::VerifySchemaBuffer(re_verifier)) return 0;

  // If we have json data and a root_struct_def, try parsing JSON.
  if (json_len > 0 && parser.root_struct_def_) {
    std::string json_str(reinterpret_cast<const char *>(json_data), json_len);
    auto json_input = std::string(json_str.c_str());
    if (json_input.size() > 0 && json_input.size() <= 8192) {
      if (parser.ParseJson(json_input.c_str())) {
        // If JSON parsed successfully, generate text back.
        std::string text_output;
        flatbuffers::GenText(parser, parser.builder_.GetBufferPointer(),
                             &text_output);
        (void)text_output;
      }
    }
  }

  return 0;
}
