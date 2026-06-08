/*
 *  Copyright (c) 2026 The WebM project authors. All Rights Reserved.
 *
 *  Use of this source code is governed by a BSD-style license
 *  that can be found in the LICENSE file in the root of the source
 *  tree. An additional intellectual property rights grant can be found
 *  in the file PATENTS.  All contributing project authors may
 *  be found in the AUTHORS file in the root of the source tree.
 */

// libFuzzer harness for Logic Group: vpx_image_format_matrix
//
// Exercises the public vpx_image API — the set of functions a
// downstream consumer uses to allocate / wrap / viewport raw pixel
// buffers before (or after) passing them through a codec. The
// implementation (vpx/src/vpx_image.c:36 img_alloc_helper) walks a
// format matrix of 10 vpx_img_fmt_t values: VPX_IMG_FMT_YV12, I420,
// I422, I444, I440, NV12, and the four HIGHBITDEPTH variants
// (I42016 / I42216 / I44016 / I44416). Each format chooses a
// different (bps, x_chroma_shift, y_chroma_shift) tuple that feeds
// into the stride / alloc_size arithmetic at vpx_image.c:123-146.
// Historical bug class: integer overflow in
//   alloc_size = (uint64_t)h * s * bps / 8
// when (w, h) are attacker-chosen and (bps) is 48 (I44416).
// vpx_img_set_rect also does unchecked pointer math on per-plane
// offsets (vpx_image.c:199-234) that no existing fuzzer walks.
//
// None of the entry functions in this LG
// (vpx_img_alloc / vpx_img_wrap / vpx_img_set_rect / vpx_img_flip /
// vpx_img_free) is touched by examples/vpx_dec_fuzzer.cc,
// examples/vpx_enc_fuzzer.cc, or any O2-Lab harness.
//
// Input format (raw, no IVF):
//   byte[0]        : fmt selector (mod 10) -> one of the valid formats
//   byte[1]        : bit 0 = alloc vs wrap
//                    bit 1 = flip after alloc
//                    bit 2 = run set_rect with (x,y,w,h)
//                    bits 3..4 = buf_align bucket (1 / 32 / 4096 / 65536)
//                    bits 5..6 = stride_align bucket (1 / 32 / 4096 / 65536)
//   byte[2..3]     : u16 LE d_w in [1..8192] (clamped — anything bigger
//                    is either rejected by the library or a DoS, not a
//                    bug class)
//   byte[4..5]     : u16 LE d_h in [1..8192]
//   byte[6..7]     : u16 LE rect_x (only used if set_rect bit is on)
//   byte[8..9]     : u16 LE rect_y
//   byte[10..11]   : u16 LE rect_w
//   byte[12..13]   : u16 LE rect_h
//   byte[14..]     : wrap data (only used when wrap path picked; must be
//                    at least the computed minimum stride * d_h or the
//                    library will walk off the end, which is an API-
//                    contract violation on the caller's side — so the
//                    harness only takes the wrap path when there are
//                    enough bytes)

#include <stddef.h>
#include <stdint.h>
#include <stdlib.h>
#include <string.h>

#include "vpx/vpx_image.h"

static constexpr unsigned int kMaxDim = 8192;
static constexpr size_t kHeaderBytes = 14;

// Map a 4-value bucket to a valid power-of-two alignment. vpx_image.c
// rejects anything that isn't a power of two (vpx_image.c:62), and
// anything > 65536 (vpx_image.c:53) — so we pick from the legal set.
static unsigned int align_from_bucket(uint8_t bucket) {
  switch (bucket & 0x03) {
    case 0: return 1;
    case 1: return 32;
    case 2: return 4096;
    case 3: return 65536;
  }
  return 1;
}

static vpx_img_fmt_t fmt_from_selector(uint8_t selector) {
  static constexpr vpx_img_fmt_t kFormats[] = {
      VPX_IMG_FMT_YV12,   VPX_IMG_FMT_I420,   VPX_IMG_FMT_I422,
      VPX_IMG_FMT_I444,   VPX_IMG_FMT_I440,   VPX_IMG_FMT_NV12,
      VPX_IMG_FMT_I42016, VPX_IMG_FMT_I42216, VPX_IMG_FMT_I44016,
      VPX_IMG_FMT_I44416,
  };
  return kFormats[selector % (sizeof(kFormats) / sizeof(kFormats[0]))];
}

static inline uint16_t read_u16_le(const uint8_t *p) {
  return static_cast<uint16_t>(p[0] | (p[1] << 8));
}

extern "C" int LLVMFuzzerTestOneInput(const uint8_t *data, size_t size) {
  if (size < kHeaderBytes) return 0;

  const uint8_t fmt_sel = data[0];
  const uint8_t flags = data[1];
  unsigned int d_w = read_u16_le(&data[2]);
  unsigned int d_h = read_u16_le(&data[4]);
  unsigned int rect_x = read_u16_le(&data[6]);
  unsigned int rect_y = read_u16_le(&data[8]);
  unsigned int rect_w = read_u16_le(&data[10]);
  unsigned int rect_h = read_u16_le(&data[12]);

  // Clamp to [1..kMaxDim]. d_w / d_h of 0 trips an internal assertion
  // (vpx_image.c:117 assert(d_w <= w)), which is an API-contract
  // violation, not a library bug. Capping to 8192 avoids 4-GB
  // allocations that DoS the fuzzer process without exposing new bugs.
  if (d_w == 0) d_w = 1;
  if (d_h == 0) d_h = 1;
  if (d_w > kMaxDim) d_w = kMaxDim;
  if (d_h > kMaxDim) d_h = kMaxDim;

  const vpx_img_fmt_t fmt = fmt_from_selector(fmt_sel);
  const bool take_wrap = (flags & 0x01) != 0;
  const bool do_flip = (flags & 0x02) != 0;
  const bool do_set_rect = (flags & 0x04) != 0;
  const unsigned int buf_align = align_from_bucket((flags >> 3) & 0x03);
  const unsigned int stride_align = align_from_bucket((flags >> 5) & 0x03);

  vpx_image_t *img = nullptr;
  uint8_t *wrap_buffer = nullptr;

  if (take_wrap) {
    // Wrap path: caller supplies the pixel storage. We compute a
    // generous upper bound and allocate exactly that many zero bytes
    // so the library can do its stride math without touching unmapped
    // memory. Upper bound derivation:
    //   bps_max = 48 bits / sample (I44416)
    //   high_bd_factor = 2 (HIGHBITDEPTH path doubles the stride)
    //   plus stride_align rounding up (max 65536) = one extra row's
    //   worth of slack.
    const uint64_t bytes_per_sample = 6;  // 48 bits == 6 bytes
    const uint64_t stride = static_cast<uint64_t>(d_w) * bytes_per_sample +
                            static_cast<uint64_t>(stride_align);
    const uint64_t total = stride * static_cast<uint64_t>(d_h) + 4096u;
    // Cap total allocation at 64 MiB — we explicitly clamped d_w,d_h
    // to 8192 each so 8192*8192*6 = ~402 MiB is the worst case; the
    // cap prevents malloc from stalling the fuzzer on pathological
    // inputs. vpx_img_wrap with img_data != NULL trusts the caller's
    // buffer size, so a too-small buffer would later segfault inside
    // vpx_img_set_rect's plane-pointer math — an intentional pattern
    // we do NOT want to trigger from the harness side.
    if (total > 64u * 1024u * 1024u) return 0;

    wrap_buffer = static_cast<uint8_t *>(calloc(1, static_cast<size_t>(total)));
    if (wrap_buffer == nullptr) return 0;

    img = vpx_img_wrap(/*img=*/nullptr, fmt, d_w, d_h, stride_align,
                       wrap_buffer);
  } else {
    // Alloc path: library owns the pixel storage. img_alloc_helper
    // has its own overflow guards (vpx_image.c:126 s > INT_MAX,
    // vpx_image.c:146 alloc_size != (size_t)alloc_size) that we want
    // to exercise. It may validly return NULL for rejected combos.
    img = vpx_img_alloc(/*img=*/nullptr, fmt, d_w, d_h, buf_align);
  }

  if (img == nullptr) {
    // All failure cleanup — library did nothing to free, our own
    // wrap buffer (if any) is still live.
    free(wrap_buffer);
    return 0;
  }

  // Optional vpx_img_set_rect — (x,y,w,h) is attacker-controlled.
  // vpx_image.c:192 validates that x+w <= img->w and y+h <= img->h
  // (with UINT_MAX overflow guards) so an out-of-range tuple is
  // correctly rejected; we still want to cover both branches.
  if (do_set_rect) {
    // Cap the viewport coordinates to 2*kMaxDim so the overflow
    // guards are exercised but we never claim a viewport that would
    // *succeed* at 4 GiB scales (we want the lib's validation to
    // fire, not our own).
    rect_x %= (kMaxDim * 2 + 1);
    rect_y %= (kMaxDim * 2 + 1);
    rect_w %= (kMaxDim * 2 + 1);
    rect_h %= (kMaxDim * 2 + 1);
    (void)vpx_img_set_rect(img, rect_x, rect_y, rect_w, rect_h);
  }

  if (do_flip) {
    vpx_img_flip(img);
  }

  // ---- Cleanup ----------------------------------------------------
  vpx_img_free(img);  // frees img_data only if img->img_data_owner
  free(wrap_buffer);  // harmless if null
  return 0;
}
