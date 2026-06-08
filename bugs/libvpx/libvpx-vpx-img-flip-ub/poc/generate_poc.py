#!/usr/bin/env python3
# generate_poc.py — re-create the crashing input for libvpx-vpx-img-flip-ub.
#
# The transferred O2VM record for this finding did not carry a standalone
# crash-input file; the 14-byte PoC below is reproduced verbatim from the
# bug report's own generate_poc.py
# (projects/chromium/ubsan-libvpx-vpx-img-flip-null-alpha-plane/bug_report.md).
#
# The harness header (vpx_image_format_matrix_fuzzer.cc) decodes these bytes as:
#   byte[0]      fmt selector -> VPX_IMG_FMT_I422 (a non-alpha format)
#   byte[1]      flags: bit1 (do_flip) set -> calls vpx_img_flip
#   byte[2..3]   u16 LE d_w = 0xffff -> clamped to 8192
#   byte[4..5]   u16 LE d_h
# vpx_img_flip then computes NULL + (d_h-1)*stride[ALPHA] -> UBSan
# "applying non-zero offset N to null pointer" at vpx/src/vpx_image.c:263.
poc = bytes([
    0x01, 0xff, 0xff, 0xff, 0xff, 0x00, 0x02, 0xff,
    0xff, 0x00, 0xfa, 0x00, 0x00, 0xfa,
])
open("poc.bin", "wb").write(poc)
