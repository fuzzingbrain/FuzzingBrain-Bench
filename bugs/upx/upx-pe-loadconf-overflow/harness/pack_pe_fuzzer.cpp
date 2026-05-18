#include <stddef.h>
#include <stdint.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <unistd.h>

#include "../src/conf.h"
#include "../src/file.h"
#include "../src/packmast.h"

extern "C" int LLVMFuzzerTestOneInput(const uint8_t* data, size_t size) {
    if (size < 64) return 0;

    char infilename[256];
    char outfilename[256];
    snprintf(infilename, 256, "/tmp/libfuzzer_pe.%d.exe", getpid());
    snprintf(outfilename, 256, "/tmp/libfuzzer_pe.%d.packed.exe", getpid());

    FILE *fp = fopen(infilename, "wb");
    if (!fp) return 0;
    fwrite(data, size, 1, fp);
    fclose(fp);

    chmod(infilename, 0755);

    char argv_progname[4] = "upx";
    char argv_compress[3] = "-1";
    char argv_force[3] = "-f";
    char argv_quiet[3] = "-q";
    char argv_output[3] = "-o";

    char* argv_data[] = {argv_progname, argv_compress, argv_force, argv_quiet,
                         infilename, argv_output, outfilename};

    try {
        upx_main(7, argv_data);
    } catch(...) {
    }

    unlink(infilename);
    unlink(outfilename);
    return 0;
}
