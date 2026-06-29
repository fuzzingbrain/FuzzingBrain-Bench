#include <stddef.h>
#include <stdint.h>
#include <string.h>

#include "common/av1_config.h"

extern "C" int LLVMFuzzerTestOneInput(const uint8_t *data, size_t size) {
  if (size == 0) return 0;

  // Part 1: read_av1config — parses the raw `av1C` box body.
  {
    Av1Config cfg;
    memset(&cfg, 0, sizeof(cfg));
    size_t bytes_read = 0;
    read_av1config(data, size, &bytes_read, &cfg);
  }

  // Part 2: get_av1config_from_obu — parses a Sequence Header OBU from
  // a (possibly annex-B) buffer.  Consume the first byte as a mode
  // selector so the fuzzer can drive both paths.
  {
    const int is_annexb = data[0] & 1;
    Av1Config cfg;
    memset(&cfg, 0, sizeof(cfg));
    get_av1config_from_obu(data + 1, size - 1, is_annexb, &cfg);
  }

  return 0;
}
