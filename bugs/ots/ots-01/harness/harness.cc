#include <cstdint>
#include <cstdlib>
#include "opentype-sanitiser.h"
#include "ots-memory-stream.h"

extern "C" int LLVMFuzzerTestOneInput(const uint8_t *data, size_t size) {
  ots::OTSContext context;
  for (int tag = 0; tag < 4; tag++) {
    for (int i = 0; i < 256; i++) {
      context.SetTableAction(OTS_TAG(
        ('a' + ((tag >> 0) & 0xf)),
        ('a' + ((tag >> 4) & 0xf)),
        ('a' + ((i >> 0) & 0xf)),
        ('a' + ((i >> 4) & 0xf))
      ), ots::TABLE_ACTION_PASSTHRU);
    }
  }
  // Set all tables to passthrough
  context.SetTableAction(0, ots::TABLE_ACTION_PASSTHRU);

  ots::ExpandingMemoryStream output(size, size * 2);
  context.Process(&output, data, size);
  return 0;
}
