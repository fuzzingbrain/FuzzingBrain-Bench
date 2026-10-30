#include <stdint.h>
#include <stdlib.h>
#include <string.h>

#include <ft2build.h>
#include FT_FREETYPE_H
#include FT_GLYPH_H
#include FT_OUTLINE_H
#include FT_BBOX_H
#include FT_STROKER_H

#define MAX_GLYPHS 512

int LLVMFuzzerTestOneInput(const uint8_t *data, size_t size) {
  FT_Library library;
  FT_Face face;
  FT_Error error;
  FT_Stroker stroker;

  if (size < 10) {
    return 0;
  }

  error = FT_Init_FreeType(&library);
  if (error) {
    return 0;
  }

  /* Try to load font from memory */
  error = FT_New_Memory_Face(library, data, (FT_Long)size, 0, &face);
  if (error) {
    FT_Done_FreeType(library);
    return 0;
  }

  /* Set various character sizes */
  FT_UInt sizes[] = {8, 12, 16, 24, 32, 48, 64};
  FT_UInt size_idx = data[0] % (sizeof(sizes) / sizeof(sizes[0]));
  FT_Set_Char_Size(face, 0, sizes[size_idx] * 64, 72, 72);

  /* Try different rendering modes */
  FT_Render_Mode modes[] = {
    FT_RENDER_MODE_NORMAL,
    FT_RENDER_MODE_LIGHT,
    FT_RENDER_MODE_MONO,
    FT_RENDER_MODE_LCD,
    FT_RENDER_MODE_LCD_V
  };
  FT_Render_Mode mode = modes[data[1] % (sizeof(modes) / sizeof(modes[0]))];

  /* Create stroker for outline operations */
  error = FT_Stroker_New(library, &stroker);
  if (!error) {
    FT_Fixed radius = (data[2] % 10 + 1) * 64;
    FT_Stroker_Set(stroker, radius,
                   FT_STROKER_LINECAP_ROUND,
                   FT_STROKER_LINEJOIN_ROUND,
                   0);
  }

  /* Iterate through some glyphs */
  FT_ULong num_glyphs = face->num_glyphs;
  if (num_glyphs > MAX_GLYPHS) {
    num_glyphs = MAX_GLYPHS;
  }

  for (FT_ULong i = 0; i < num_glyphs && i < 50; i++) {
    /* Load glyph with various flags */
    FT_Int32 load_flags = FT_LOAD_DEFAULT;
    if (data[3] & 0x01) load_flags |= FT_LOAD_NO_SCALE;
    if (data[3] & 0x02) load_flags |= FT_LOAD_NO_HINTING;
    if (data[3] & 0x04) load_flags |= FT_LOAD_RENDER;
    if (data[3] & 0x08) load_flags |= FT_LOAD_NO_BITMAP;
    if (data[3] & 0x10) load_flags |= FT_LOAD_VERTICAL_LAYOUT;
    if (data[3] & 0x20) load_flags |= FT_LOAD_FORCE_AUTOHINT;

    error = FT_Load_Glyph(face, i, load_flags);
    if (error) {
      continue;
    }

    /* Try to render with specified mode */
    if (face->glyph->format == FT_GLYPH_FORMAT_OUTLINE) {
      FT_Render_Glyph(face->glyph, mode);

      /* Test outline operations */
      FT_Outline *outline = &face->glyph->outline;

      /* Get outline bbox */
      FT_BBox bbox;
      FT_Outline_Get_BBox(outline, &bbox);

      /* Try outline transformations */
      if (data[4] & 0x01) {
        FT_Matrix matrix;
        matrix.xx = 0x10000L;
        matrix.xy = 0;
        matrix.yx = 0;
        matrix.yy = 0x10000L;
        FT_Outline_Transform(outline, &matrix);
      }

      /* Try outline translation */
      if (data[4] & 0x02) {
        FT_Outline_Translate(outline, 100, 100);
      }

      /* Test stroker if available */
      if (stroker) {
        FT_Glyph glyph;
        error = FT_Get_Glyph(face->glyph, &glyph);
        if (!error) {
          if (glyph->format == FT_GLYPH_FORMAT_OUTLINE) {
            /* destroy=1 tells FT_Glyph_Stroke to free the original glyph */
            FT_Glyph_Stroke(&glyph, stroker, 1);
          }
          FT_Done_Glyph(glyph);
        }
      }
    }

    /* Test glyph copying */
    FT_Glyph glyph;
    error = FT_Get_Glyph(face->glyph, &glyph);
    if (!error) {
      FT_Done_Glyph(glyph);
    }
  }

  /* Cleanup */
  if (stroker) {
    FT_Stroker_Done(stroker);
  }
  FT_Done_Face(face);
  FT_Done_FreeType(library);

  return 0;
}
