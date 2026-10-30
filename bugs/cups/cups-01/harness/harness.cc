#include <stddef.h>
#include <stdint.h>
#include <stdlib.h>
#include <string.h>
#include <cups/transcode.h>

extern "C" int LLVMFuzzerTestOneInput(const uint8_t *data, size_t size) {
  cups_utf8_t *src = (cups_utf8_t *)malloc(size + 1);
  if (!src) return 0;
  memcpy(src, data, size);
  src[size] = 0;                          // NUL-terminate at the exact end
  char dest[2048];
  cupsUTF8ToCharset(dest, src, (int)sizeof(dest), CUPS_ISO8859_1);
  free(src);
  return 0;
}
