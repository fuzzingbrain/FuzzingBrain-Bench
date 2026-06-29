#include <cstdint>
#include <cstdlib>
#include "opentype-sanitiser.h"
#include "ots-memory-stream.h"

namespace {
class PassthruContext : public ots::OTSContext {
public:
    ots::TableAction GetTableAction(uint32_t /*tag*/) override {
        return ots::TABLE_ACTION_PASSTHRU;
    }
};
}  // namespace

extern "C" int LLVMFuzzerTestOneInput(const uint8_t *data, size_t size) {
    if (size == 0 || size > 64 * 1024 * 1024) return 0;
    PassthruContext context;
    ots::ExpandingMemoryStream output(size, size * 2);
    context.Process(&output, data, size);
    return 0;
}
