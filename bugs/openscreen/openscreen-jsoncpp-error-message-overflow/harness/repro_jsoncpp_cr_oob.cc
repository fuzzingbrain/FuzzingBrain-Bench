// repro_jsoncpp_cr_oob.cc
//
// Path-B standalone reproduction for openscreen-jsoncpp-error-message-overflow.
// Reproduces the exact Json::CharReader::parse(begin, end, &root, &errs) call
// shape that openscreen::json::Parse uses
// (third_party/openscreen/src/util/json/json_serialization.cc:29). A 1-byte
// input ending in CR (0x0d) makes jsoncpp's error formatter
// (getFormattedErrorMessages -> getLocationLineAndColumn) peek one byte past
// the heap buffer at json_reader.cpp:1828 (the CR-LF look-ahead).
//
// Verbatim from the discovery repro bundle
// (crash-11f4de6b...repro/repro_jsoncpp_cr_oob.cc).

#include <json/reader.h>
#include <json/value.h>
#include <cstdio>
#include <cstring>
#include <fstream>
#include <memory>
#include <sstream>
#include <string>

int main(int argc, char** argv) {
  if (argc != 2) {
    std::fprintf(stderr, "Usage: %s <poc.bin>\n", argv[0]);
    return 1;
  }
  std::ifstream f(argv[1], std::ios::binary);
  std::ostringstream ss;
  ss << f.rdbuf();
  const std::string raw = ss.str();

  // Use a heap allocation so ASan places a redzone immediately after
  // the last byte (matches the libFuzzer / openscreen call shape).
  char* buf = new char[raw.size()];
  std::memcpy(buf, raw.data(), raw.size());

  Json::CharReaderBuilder builder;
  Json::CharReaderBuilder::strictMode(&builder.settings_);
  std::unique_ptr<Json::CharReader> reader(builder.newCharReader());
  Json::Value root;
  std::string errs;
  // Two-pointer parse — same call shape as
  // openscreen::json::Parse at
  // third_party/openscreen/src/util/json/json_serialization.cc:29.
  reader->parse(buf, buf + raw.size(), &root, &errs);

  delete[] buf;
  return 0;
}
