// libFuzzer harness for the cupsUTF8ToCharset() truncated-UTF-8 OOB read.
// The untrusted input is the UTF-8 source string; the call itself is a valid
// use of the public API (dest buffer + maxout are correct). The overflow is
// internal: a trailing 2-byte lead byte makes the decoder read past the
// NUL terminator. We heap-allocate the NUL-terminated copy so ASan guards
// the end of the buffer.
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
