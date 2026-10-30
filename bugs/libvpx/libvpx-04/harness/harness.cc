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

    // buffer size, so a too-small buffer would later segfault inside
    // vpx_img_set_rect's plane-pointer math — an intentional pattern

    if (total > 64u * 1024u * 1024u) return 0;

    wrap_buffer = static_cast<uint8_t *>(calloc(1, static_cast<size_t>(total)));
    if (wrap_buffer == nullptr) return 0;

    img = vpx_img_wrap(/*img=*/nullptr, fmt, d_w, d_h, stride_align,
                       wrap_buffer);
  } else {
    // Alloc path: library owns the pixel storage. img_alloc_helper

    // vpx_image.c:146 alloc_size != (size_t)alloc_size) that we want

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

  // correctly rejected; we still want to cover both branches.
  if (do_set_rect) {

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
  free(wrap_buffer);
  return 0;
}
