// pack_file_fuzzer.cpp
#include <stddef.h>
#include <stdint.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <unistd.h>

#include "../src/conf.h"

extern "C" int LLVMFuzzerTestOneInput(const uint8_t* data, size_t size) {
  if (size < 64) return 0;

  char infilename[256], outfilename[256];
  snprintf(infilename, 256, "/tmp/libfuzzer_pack.%d", getpid());
  snprintf(outfilename, 256, "/tmp/libfuzzer_pack.%d.packed", getpid());

  FILE *fp = fopen(infilename, "wb");
  if (!fp) return 0;
  fwrite(data, size, 1, fp);
  fclose(fp);
  chmod(infilename, 0755);

  char* argv[] = {"upx", "-1", "-f", "-q", infilename, "-o", outfilename};
  try { upx_main(7, argv); } catch(...) {}

  unlink(infilename);
  unlink(outfilename);
  return 0;
}
