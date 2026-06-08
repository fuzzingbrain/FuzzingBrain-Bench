/*
 * Copyright 2014 Google Inc. All rights reserved.
 *
 * Licensed under the Apache License, Version 2.0 (the "License");
 * you may not use this file except in compliance with the License.
 * You may obtain a copy of the License at
 *
 *     http://www.apache.org/licenses/LICENSE-2.0
 *
 * Unless required by applicable law or agreed to in writing, software
 * distributed under the License is distributed on an "AS IS" BASIS,
 * WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
 * See the License for the specific language governing permissions and
 * limitations under the License.
 */

// libFuzzer harness for Logic Group: flatbuffers_reflection_gentext
//
// Exercises the reflection-driven text generation path:
//   Parser::Deserialize(bfbs) -- one-time in Initialize
//   reflection::Verify(schema, root, buf, len) -- per call
//   GenText(parser, buf, &dest) / GenTextFromTable -- the payload
//
// The existing flatbuffers_monster_fuzzer.cc path uses the same
// GenText call, but only after a successful ParseJson(). That
// means the buffer fed to GenText is always a builder-produced
// buffer — there's no "malicious raw bytes that survived Verify"
// path. This harness is that second path: feed raw fuzz bytes to
// reflection::Verify, on success hand them straight to GenText.
// The two paths exercise different sub-trees of the text
// generator (reflection-based vs Parser::root_struct_def_).

#include <stddef.h>
#include <stdint.h>

#include <filesystem>
#include <string>
#include <vector>

#include "flatbuffers/idl.h"
#include "flatbuffers/reflection.h"
#include "flatbuffers/reflection_generated.h"
#include "flatbuffers/util.h"
#include "flatbuffers/verifier.h"

namespace {

// Initialized once by LLVMFuzzerInitialize from monster_test.bfbs.
static flatbuffers::Parser* g_parser = nullptr;
static std::string g_schema_bfbs;
static bool g_init_ok = false;

static bool LoadFileRelative(const std::filesystem::path& exe_path,
                             const char* file_name, bool binary,
                             std::string* out) {
  const auto file_path = exe_path.parent_path() / file_name;
  if (!std::filesystem::exists(file_path)) return false;
  return flatbuffers::LoadFile(file_path.string().c_str(), binary, out);
}

}  // namespace

extern "C" int LLVMFuzzerInitialize(int* /*argc*/, char*** argv) {
  std::filesystem::path exe_path((*argv)[0]);
  if (!LoadFileRelative(exe_path, "monster_test.bfbs", true, &g_schema_bfbs)) {
    g_init_ok = false;
    return 0;
  }

  // Verify the schema buffer up-front.
  flatbuffers::Verifier schema_verifier(
      reinterpret_cast<const uint8_t*>(g_schema_bfbs.c_str()),
      g_schema_bfbs.size());
  if (!reflection::VerifySchemaBuffer(schema_verifier)) {
    g_init_ok = false;
    return 0;
  }

  // Create the Parser and deserialize the schema into it. This is
  // the same setup the in-tree flatbuffers_monster_fuzzer.cc does,
  // so we inherit its root_struct_def_ for GenText.
  g_parser = new flatbuffers::Parser();
  const bool ok = g_parser->Deserialize(
      reinterpret_cast<const uint8_t*>(g_schema_bfbs.c_str()),
      g_schema_bfbs.size());
  if (!ok || g_parser->root_struct_def_ == nullptr) {
    delete g_parser;
    g_parser = nullptr;
    g_init_ok = false;
    return 0;
  }
  g_init_ok = true;
  return 0;
}

extern "C" int LLVMFuzzerTestOneInput(const uint8_t* data, size_t size) {
  if (!g_init_ok || g_parser == nullptr) return 0;
  if (size < flatbuffers::kFileIdentifierLength + sizeof(flatbuffers::uoffset_t))
    return 0;
  if (size > (1u << 18)) return 0;

  // Step 1: reflection-based verify. Same schema the Parser holds.
  // Uses documented max_depth=64 / max_tables=1e6 defaults.
  const reflection::Schema* schema_ptr =
      reflection::GetSchema(g_schema_bfbs.c_str());
  if (schema_ptr == nullptr) return 0;
  const reflection::Object* root_def = schema_ptr->root_table();
  if (root_def == nullptr) return 0;

  if (!flatbuffers::Verify(*schema_ptr, *root_def, data, size,
                           /*max_depth=*/64, /*max_tables=*/1000000)) {
    return 0;
  }

  // Step 2: run GenText via the Parser's root_struct_def_.
  // GenText returns nullptr on success, else an error string.
  {
    std::string dest;
    const char* err = flatbuffers::GenText(*g_parser, data, &dest);
    (void)err;
  }

  // Step 3: also run GenTextFromTable with the explicit table name
  // from the parser's struct def. This is the alternative entry
  // that the reflection-driven path takes when the caller knows
  // the type name at runtime.
  {
    std::string dest;
    const char* err = flatbuffers::GenTextFromTable(
        *g_parser, data, g_parser->root_struct_def_->name, &dest);
    (void)err;
  }

  return 0;
}
