#include <cstddef>
#include <cstdint>
#include <string>
#include <vector>

#include "flatbuffers/flexbuffers.h"

// Recursively traverse a flexbuffers Reference to exercise all accessors.
static void TraverseReference(flexbuffers::Reference ref, int depth) {
  if (depth > 10) return;  // Bound recursion.

  // Exercise type queries.
  (void)ref.IsNull();
  (void)ref.IsInt();
  (void)ref.IsUInt();
  (void)ref.IsFloat();
  (void)ref.IsString();
  (void)ref.IsKey();
  (void)ref.IsVector();
  (void)ref.IsMap();
  (void)ref.IsBlob();
  (void)ref.IsBool();
  (void)ref.IsNumeric();

  // Exercise scalar conversions.
  (void)ref.AsInt64();
  (void)ref.AsUInt64();
  (void)ref.AsDouble();
  (void)ref.AsFloat();
  (void)ref.AsInt32();
  (void)ref.AsInt16();
  (void)ref.AsInt8();
  (void)ref.AsUInt32();
  (void)ref.AsUInt16();
  (void)ref.AsUInt8();
  (void)ref.AsBool();

  // Exercise string conversion.
  auto str = ref.ToString();
  (void)str;

  if (ref.IsString() || ref.IsKey()) {
    auto s = ref.AsString();
    (void)s.c_str();
    (void)s.length();
  }

  if (ref.IsBlob()) {
    auto blob = ref.AsBlob();
    (void)blob.data();
    (void)blob.size();
  }

  if (ref.IsVector()) {
    auto vec = ref.AsVector();
    for (size_t i = 0; i < vec.size() && i < 32; i++) {
      TraverseReference(vec[i], depth + 1);
    }
  }

  if (ref.IsMap()) {
    auto map = ref.AsMap();
    auto keys = map.Keys();
    auto vals = map.Values();
    for (size_t i = 0; i < keys.size() && i < 32; i++) {
      TraverseReference(keys[i], depth + 1);
      TraverseReference(vals[i], depth + 1);
    }
  }

  // Exercise typed vector accessors.
  if (ref.IsTypedVector()) {
    auto tv = ref.AsTypedVector();
    for (size_t i = 0; i < tv.size() && i < 32; i++) {
      (void)tv[i].AsInt64();
    }
  }

  if (ref.IsFixedTypedVector()) {
    auto ftv = ref.AsFixedTypedVector();
    for (size_t i = 0; i < ftv.size() && i < 4; i++) {
      (void)ftv[i].AsDouble();
    }
  }
}

extern "C" int LLVMFuzzerTestOneInput(const uint8_t *data, size_t size) {
  if (size < 3 || size > 65536) return 0;

  std::vector<uint8_t> reuse_tracker;
  if (!flexbuffers::VerifyBuffer(data, size, &reuse_tracker)) {
    return 0;
  }

  // Only reach here with verified buffers, exercise deep accessor paths.
  auto root = flexbuffers::GetRoot(data, size);
  TraverseReference(root, 0);

  return 0;
}
