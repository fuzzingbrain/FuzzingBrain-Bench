#include <stddef.h>
#include <stdint.h>
#include <stdlib.h>
#include <string.h>

#include <hb.h>
#include <hb-fontations.h>

int LLVMFuzzerTestOneInput(const uint8_t *data, size_t size) {
    if (size < 4 || size > (4u << 20)) return 0;

    hb_blob_t *blob = hb_blob_create((const char *)data, (unsigned)size,
                                     HB_MEMORY_MODE_READONLY, NULL, NULL);
    if (!blob) return 0;

    hb_face_t *face = hb_face_create(blob, 0);
    hb_font_t *font = hb_font_create(face);
    hb_fontations_font_set_funcs(font);   

    char buf[1];
    hb_font_get_glyph_name(font, 0, buf, 0);   

    hb_font_destroy(font);
    hb_face_destroy(face);
    hb_blob_destroy(blob);
    return 0;
}
