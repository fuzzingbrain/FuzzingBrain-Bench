/*
 * Fuzzer for VP9 encoder with varied configuration options.
 *
 * Tests: vpx_codec_enc_config_default, vpx_codec_enc_init,
 *        vpx_codec_encode, vpx_codec_get_cx_data,
 *        vpx_codec_control (encoder-side controls),
 *        vpx_codec_destroy.
 *
 * Security target: encoder configuration validation and encoding
 *                  with diverse rate control / spatial layer settings.
 */

#include <stddef.h>
#include <stdint.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>

#include "vpx/vp8cx.h"
#include "vpx/vpx_encoder.h"

#define FUZZ_HDR_SZ 48

extern "C" void usage_exit(void) { exit(EXIT_FAILURE); }

static int vpx_img_plane_width(const vpx_image_t *img, int plane) {
  if (plane > 0 && img->x_chroma_shift > 0)
    return (img->d_w + 1) >> img->x_chroma_shift;
  else
    return img->d_w;
}

static int vpx_img_plane_height(const vpx_image_t *img, int plane) {
  if (plane > 0 && img->y_chroma_shift > 0)
    return (img->d_h + 1) >> img->y_chroma_shift;
  else
    return img->d_h;
}

static size_t fill_image(vpx_image_t *img, const uint8_t *data, size_t size) {
  size_t used = 0;
  for (int plane = 0; plane < 3; ++plane) {
    unsigned char *buf = img->planes[plane];
    const int stride = img->stride[plane];
    const int w = vpx_img_plane_width(img, plane);
    const int h = vpx_img_plane_height(img, plane);
    for (int y = 0; y < h; ++y) {
      size_t nb = (size_t)w;
      if (nb > size - used) nb = size - used;
      memcpy(buf, data + used, nb);
      if (nb < (size_t)w) memset(buf + nb, 0, w - nb);
      buf += stride;
      used += nb;
    }
  }
  return used;
}

extern "C" int LLVMFuzzerTestOneInput(const uint8_t *data, size_t size) {
  if (size <= FUZZ_HDR_SZ) return 0;

  vpx_codec_ctx_t codec;
  vpx_image_t raw;
  vpx_codec_enc_cfg_t cfg;

  if (vpx_codec_enc_config_default(vpx_codec_vp9_cx(), &cfg, 0)) return 0;

  // Parse config from fuzz header
  // Byte 0: quality mode
  vpx_enc_deadline_t quality;
  switch (data[0] & 0x03) {
    case 0: quality = VPX_DL_REALTIME; break;
    case 1: quality = VPX_DL_GOOD_QUALITY; break;
    case 2: quality = VPX_DL_BEST_QUALITY; break;
    default: quality = VPX_DL_REALTIME; break;
  }

  // Byte 1: dimensions
  switch (data[1] & 0x07) {
    case 0: cfg.g_w = 2; cfg.g_h = 2; break;
    case 1: cfg.g_w = 4; cfg.g_h = 4; break;
    case 2: cfg.g_w = 8; cfg.g_h = 8; break;
    case 3: cfg.g_w = 16; cfg.g_h = 16; break;
    case 4: cfg.g_w = 32; cfg.g_h = 24; break;
    case 5: cfg.g_w = 64; cfg.g_h = 48; break;
    case 6: cfg.g_w = 1; cfg.g_h = 1; break;
    default: cfg.g_w = 16; cfg.g_h = 16; break;
  }

  // Byte 2: rate control mode
  switch (data[2] & 0x03) {
    case 0: cfg.rc_end_usage = VPX_VBR; break;
    case 1: cfg.rc_end_usage = VPX_CBR; break;
    case 2: cfg.rc_end_usage = VPX_CQ; break;
    case 3: cfg.rc_end_usage = VPX_Q; break;
  }

  // Byte 3: thread count [1, 4]
  cfg.g_threads = (data[3] & 0x03) + 1;

  // Byte 4: target bitrate
  cfg.rc_target_bitrate = ((data[4] << 8) | data[5]) % 2000 + 10;

  // Byte 6: temporal/spatial scalability settings
  cfg.g_timebase.num = 1;
  cfg.g_timebase.den = (data[6] & 0x01) ? 60 : 30;

  // Byte 7: error resilience
  cfg.g_error_resilient = (data[7] & 0x01) ? 1 : 0;

  // Byte 8: lag_in_frames
  cfg.g_lag_in_frames = (quality == VPX_DL_BEST_QUALITY) ? 0 : (data[8] & 0x03);

  // Byte 9: keyframe mode
  if (data[9] & 0x01) {
    cfg.kf_mode = VPX_KF_DISABLED;
  } else {
    cfg.kf_mode = VPX_KF_AUTO;
    cfg.kf_min_dist = 0;
    cfg.kf_max_dist = (data[9] >> 1) & 0x1f;
  }

  // Byte 10: profile [0-3]
  cfg.g_profile = data[10] & 0x03;

  // Bytes 11-12: quantizer range
  cfg.rc_min_quantizer = data[11] % 64;
  cfg.rc_max_quantizer = cfg.rc_min_quantizer + (data[12] % (64 - cfg.rc_min_quantizer));

  // Max frames limited for performance
  const int max_frames = (quality == VPX_DL_BEST_QUALITY) ? 20 : 50;

  // Choose pixel format based on profile
  vpx_img_fmt_t img_fmt = VPX_IMG_FMT_I420;
  if (cfg.g_profile == 1) {
    img_fmt = VPX_IMG_FMT_I422;
  } else if (cfg.g_profile == 2) {
    img_fmt = VPX_IMG_FMT_I42016;
  } else if (cfg.g_profile == 3) {
    img_fmt = VPX_IMG_FMT_I42216;
  }

  vpx_codec_flags_t enc_flags = 0;
  if (cfg.g_profile >= 2) {
    enc_flags |= VPX_CODEC_USE_HIGHBITDEPTH;
  }

  if (vpx_codec_enc_init(&codec, vpx_codec_vp9_cx(), &cfg, enc_flags) !=
      VPX_CODEC_OK) {
    return 0;
  }

  if (!vpx_img_alloc(&raw, img_fmt, cfg.g_w, cfg.g_h, 1)) {
    vpx_codec_destroy(&codec);
    return 0;
  }

  // Apply encoder controls from fuzz bytes 13-20
  // Set CPU usage / speed
  int cpu_used = (data[13] & 0x0f) % 10;
  vpx_codec_control(&codec, VP8E_SET_CPUUSED, cpu_used);

  // Noise sensitivity
  vpx_codec_control(&codec, VP9E_SET_NOISE_SENSITIVITY, data[14] & 0x01);

  // AQ mode (0-3)
  vpx_codec_control(&codec, VP9E_SET_AQ_MODE, data[15] & 0x03);

  // Tile columns (0-6 for log2)
  vpx_codec_control(&codec, VP9E_SET_TILE_COLUMNS, data[16] & 0x03);

  // Tile rows (0-2 for log2)
  vpx_codec_control(&codec, VP9E_SET_TILE_ROWS, data[17] & 0x01);

  const uint8_t *payload = data + FUZZ_HDR_SZ;
  size_t payload_size = size - FUZZ_HDR_SZ;

  int frame_count = 0;
  int keyframe_interval = (data[18] & 0x0f) + 1;

  for (int i = 0; i < max_frames; ++i) {
    size_t read = fill_image(&raw, payload, payload_size);
    if (read == 0) break;
    payload += read;
    payload_size -= read;

    int flags = 0;
    if (keyframe_interval > 0 && frame_count % keyframe_interval == 0)
      flags |= VPX_EFLAG_FORCE_KF;

    vpx_codec_err_t res =
        vpx_codec_encode(&codec, &raw, frame_count++, 1, flags, quality);
    if (res != VPX_CODEC_OK) break;

    // Drain output packets
    vpx_codec_iter_t iter = nullptr;
    const vpx_codec_cx_pkt_t *pkt;
    while ((pkt = vpx_codec_get_cx_data(&codec, &iter)) != nullptr) {
      // Just consume the output
      (void)pkt;
    }
  }

  // Flush encoder
  for (int i = 0; i < 10; ++i) {
    vpx_codec_err_t res =
        vpx_codec_encode(&codec, nullptr, -1, 1, 0, quality);
    if (res != VPX_CODEC_OK) break;

    vpx_codec_iter_t iter = nullptr;
    const vpx_codec_cx_pkt_t *pkt;
    int got = 0;
    while ((pkt = vpx_codec_get_cx_data(&codec, &iter)) != nullptr) {
      got = 1;
    }
    if (!got) break;
  }

  vpx_img_free(&raw);
  vpx_codec_destroy(&codec);
  return 0;
}
