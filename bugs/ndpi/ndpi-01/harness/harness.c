#include "ndpi_api.h"

#include <stdint.h>
#include <stdlib.h>

int LLVMFuzzerTestOneInput(const uint8_t *data, size_t size) {
  u_int8_t num_blocks = 0;
  struct ndpi_tls_block *blocks;

  if (size > (u_int)UINT32_MAX)
    return 0;

  blocks = ndpi_decode_tls_blocks((const u_char *)data,
                                  (u_int)size,
                                  &num_blocks);
  if (blocks != NULL)
    ndpi_free(blocks);

  return 0;
}
