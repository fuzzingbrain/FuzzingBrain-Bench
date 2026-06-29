#include <stddef.h>
#include <stdint.h>
#include <stdlib.h>
#include <string.h>
#include <avif/avif.h>

extern "C" int LLVMFuzzerTestOneInput(const uint8_t *data, size_t size) {
    if (size < 4 || size > (4u << 20)) return 0;

    avifDecoder *decoder = avifDecoderCreate();
    if (!decoder) return 0;

    decoder->maxThreads = 1;
    decoder->ignoreXMP = AVIF_TRUE;
    decoder->ignoreExif = AVIF_TRUE;
    decoder->strictFlags = 0;

    // Make a copy of the input and tell libavif it's SIZE_MAX bytes long.
    // (Mirrors what the JNI bug does when Java passes int length = -1.)
    uint8_t *buffer = (uint8_t *) malloc(size);
    if (!buffer) {
        avifDecoderDestroy(decoder);
        return 0;
    }
    memcpy(buffer, data, size);

    // The sign-extension bug — pass SIZE_MAX as the buffer length.
    avifResult res = avifDecoderSetIOMemory(decoder, buffer, (size_t) -1);
    if (res == AVIF_RESULT_OK) {
        (void) avifDecoderParse(decoder);  // walks off the end of `buffer`
    }

    avifDecoderDestroy(decoder);
    free(buffer);
    return 0;
}
