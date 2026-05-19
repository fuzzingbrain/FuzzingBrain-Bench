/*
 * Corrected harness for ots-processgeneric-npd.
 *
 * The agent-extracted fuzz_ots_passthru.cc in this directory uses a
 * SetTableAction() API that does not exist on ots::OTSContext at the
 * bug's vuln_commit. The actual OTS API requires subclassing
 * OTSContext and overriding the virtual GetTableAction(tag) hook.
 *
 * This wrapper provides exactly that: a PassthruContext that returns
 * TABLE_ACTION_PASSTHRU for every tag, then drives Process() on the
 * fuzz input. The end behavior matches the intent of the extracted
 * harness (force PASSTHRU on every table -> hit the maxp NPD code
 * path in ProcessGeneric).
 *
 * fuzz_ots_passthru.cc stays alongside this file for provenance
 * tracing — see harness/PROVENANCE.md.
 */
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
