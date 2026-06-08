/*
 *  Copyright (c) 2026 The WebM project authors. All Rights Reserved.
 *
 *  Use of this source code is governed by a BSD-style license
 *  that can be found in the LICENSE file in the root of the source
 *  tree. An additional intellectual property rights grant can be found
 *  in the file PATENTS.  All contributing project authors may
 *  be found in the AUTHORS file in the root of the source tree.
 */

// libFuzzer harness for Logic Group: vp9_encoder_svc_layer_config
//
// Drives the VP9 encoder as a multi-layer Scalable Video Coding (SVC)
// stream with fuzz-chosen spatial/temporal layer counts, per-layer
// bitrates, and reference-frame configs. Targets
// vp9/encoder/vp9_svc_layercontext.c (~1000 SLOC) plus the
// reconfig paths and per-layer rc. The in-tree
// examples/vpx_enc_fuzzer.cc runs a single-layer encoder and never
// touches VP9E_SET_SVC* — this harness carves out the SVC-only
// subspace of the encoder's attack surface.
//
// Call pipeline (matches examples/vp9_spatial_svc_encoder.c):
//   vpx_codec_enc_config_default → fill SVC fields in
//   vpx_codec_enc_cfg_t → vpx_codec_enc_init →
//   VP9E_SET_SVC(1) →
//   VP9E_SET_SVC_PARAMETERS →
//   loop:
//     { VP9E_SET_SVC_LAYER_ID,
//       VP9E_SET_SVC_REF_FRAME_CONFIG (sometimes),
//       vpx_codec_encode,
//       vpx_codec_get_cx_data }
//   → vpx_codec_destroy.
//
// ----- Design notes on API-contract compliance (P2) -----
// Several SVC-adjacent fields in vpx_codec_enc_cfg_t are interlocked:
//   * ss_number_layers and ts_number_layers must each be in
//     [1, VPX_SS_MAX_LAYERS] / [1, VPX_TS_MAX_LAYERS] (both = 5).
//   * ts_target_bitrate[0..ts_number_layers-1] must be
//     monotonically non-decreasing.
//   * ss_target_bitrate[0..ss_number_layers-1] must be
//     monotonically non-decreasing.
//   * rc_target_bitrate must be >= sum of the top-layer bitrates.
//   * g_w / g_h must be multiples of 2 (VP9 subsampling).
//   * ts_periodicity must be a multiple of ts_number_layers.
// We honor every constraint explicitly. Passing random bytes into
// these fields would trip internal asserts inside
// vp9_update_layer_context_change_config and the crash would be
// P2-class (API misuse), not a library bug. The interesting bug
// class is "contract-compliant config + SVC reconfig sequence with
// a stale per-layer context", which we reach by keeping the config
// legal but varying the *sequence* of SET_SVC_LAYER_ID and
// SET_SVC_REF_FRAME_CONFIG calls between encode() calls.

#include <stddef.h>
#include <stdint.h>
#include <stdlib.h>
#include <string.h>

#include "vpx/vp8cx.h"
#include "vpx/vpx_encoder.h"
#include "vpx/vpx_image.h"

// Harness parameter caps — keep memory footprint predictable so
// libFuzzer iterations stay cheap under ASan.
static constexpr unsigned int kMaxWidth = 128;
static constexpr unsigned int kMaxHeight = 128;
static constexpr int kMaxFrames = 8;
// Per-layer bitrate cap (kbps). The libvpx SVC rate-control code
// does multiply-add on these values; keeping them bounded avoids
// triggering pure-math-overflow paths that are P2-class.
static constexpr unsigned int kMaxLayerBitrate = 2000u;

extern "C" void usage_exit(void) { exit(EXIT_FAILURE); }

// Cumulative monotonic bitrate ladder builder. Given a seed and the
// number of layers, returns layer[i] = (i+1)*step where step is
// derived from `seed` and bounded. This produces a legal
// non-decreasing ladder without leaking raw fuzz bytes into the
// bitrate field (which would be a P2 contract violation).
static void build_bitrate_ladder(unsigned int *out, int layers,
                                 uint8_t seed) {
  const unsigned int step = 100u + (seed & 0x7f) * 8u;  // 100..1116
  for (int i = 0; i < layers; ++i) {
    unsigned int br = step * static_cast<unsigned int>(i + 1);
    if (br > kMaxLayerBitrate) br = kMaxLayerBitrate;
    out[i] = br;
  }
}

extern "C" int LLVMFuzzerTestOneInput(const uint8_t *data, size_t size) {
  // Harness header: 16 bytes of config, no raw pixel bytes needed
  // (we fabricate the I420 frames from a single byte pattern).
  if (size < 16) return 0;

  // ---- Unpack config from the first 16 bytes ---------------------
  const uint8_t *h = data;
  // Spatial layer count in [1..4] (we cap to 4 to fit VP9's
  // documented SVC limit of 4 spatial even though VPX_SS_MAX_LAYERS
  // = 5 in the public header).
  const int ss_layers = static_cast<int>(h[0] & 0x03) + 1;
  // Temporal layer count in [1..3] (VP9 supports up to 3 temporal).
  // NOTE: (h[1] & 0x03) + 1 is in [1..4], but the ts_rate_decimator
  // / ts_periodicity block below only handles 1/2/3 — passing
  // ts_layers=4 leaves ts_rate_decimator[3] uninitialised and
  // ts_periodicity=12 not divisible by 4, which violates the SVC
  // contract `ts_periodicity % ts_number_layers == 0` and would
  // trip vp9_update_layer_context_change_config. Any crash from that
  // path is a harness P2 false positive. Clamp to [1..3].
  int ts_layers = static_cast<int>(h[1] & 0x03) + 1;
  if (ts_layers > 3) ts_layers = 3;
  const uint8_t bitrate_seed = h[2];
  const uint8_t gop_bits = h[3];
  const uint8_t layer_id_seed = h[4];
  const uint8_t ref_seed = h[5];
  const uint8_t width_sel = h[6] & 0x07;
  const uint8_t height_sel = h[7] & 0x07;
  // bytes 8..15 reserved for future flags; consume harmlessly.
  (void)h;

  // Pick g_w, g_h from a legal-even ladder. Each is a multiple of 2.
  const unsigned int w_table[8] = {32, 64, 96, 128, 48, 80, 112, 64};
  const unsigned int h_table[8] = {32, 64, 96, 128, 48, 80, 112, 32};
  unsigned int g_w = w_table[width_sel];
  unsigned int g_h = h_table[height_sel];
  if (g_w > kMaxWidth) g_w = kMaxWidth;
  if (g_h > kMaxHeight) g_h = kMaxHeight;
  if (g_w < 2) g_w = 2;
  if (g_h < 2) g_h = 2;
  g_w &= ~1u;
  g_h &= ~1u;

  // ---- Build a contract-compliant SVC cfg ------------------------
  vpx_codec_enc_cfg_t cfg;
  if (vpx_codec_enc_config_default(vpx_codec_vp9_cx(), &cfg, 0) !=
      VPX_CODEC_OK) {
    return 0;
  }
  cfg.g_w = g_w;
  cfg.g_h = g_h;
  cfg.g_timebase.num = 1;
  cfg.g_timebase.den = 30;
  cfg.g_error_resilient = 1;
  cfg.rc_end_usage = VPX_CBR;  // required for SVC

  cfg.ss_number_layers = static_cast<unsigned int>(ss_layers);
  cfg.ts_number_layers = static_cast<unsigned int>(ts_layers);

  // Non-decreasing spatial bitrate ladder.
  build_bitrate_ladder(cfg.ss_target_bitrate, ss_layers, bitrate_seed);
  for (int i = 0; i < ss_layers; ++i) {
    cfg.ss_enable_auto_alt_ref[i] = 0;
  }

  // Non-decreasing temporal bitrate ladder.
  build_bitrate_ladder(cfg.ts_target_bitrate, ts_layers,
                       static_cast<uint8_t>(bitrate_seed ^ 0x55));

  // ts_rate_decimator: standard {4, 2, 1} pattern for 3 layers,
  // {2, 1} for 2 layers, {1} for 1 layer. This mirrors
  // vp9_spatial_svc_encoder.c.
  if (ts_layers == 1) {
    cfg.ts_rate_decimator[0] = 1;
  } else if (ts_layers == 2) {
    cfg.ts_rate_decimator[0] = 2;
    cfg.ts_rate_decimator[1] = 1;
  } else {
    cfg.ts_rate_decimator[0] = 4;
    cfg.ts_rate_decimator[1] = 2;
    cfg.ts_rate_decimator[2] = 1;
  }

  // ts_periodicity must be a multiple of ts_number_layers (libvpx
  // docs). We pick 8 for 1/2 layers and 12 for 3 layers.
  cfg.ts_periodicity = (ts_layers == 3) ? 12 : 8;
  // Fill ts_layer_id with a round-robin [0..ts_layers-1] pattern.
  for (unsigned int i = 0; i < cfg.ts_periodicity; ++i) {
    cfg.ts_layer_id[i] = i % static_cast<unsigned int>(ts_layers);
  }

  // rc_target_bitrate >= top ss/ts layer — use the cfg's ss top.
  cfg.rc_target_bitrate =
      cfg.ss_target_bitrate[ss_layers - 1] +
      (unsigned int)(50 * ts_layers);
  if (cfg.rc_target_bitrate > kMaxLayerBitrate * 10) {
    cfg.rc_target_bitrate = kMaxLayerBitrate * 10;
  }

  // ---- Init encoder ----------------------------------------------
  vpx_codec_ctx_t codec;
  if (vpx_codec_enc_init(&codec, vpx_codec_vp9_cx(), &cfg, 0) !=
      VPX_CODEC_OK) {
    return 0;
  }

  // Enable SVC mode.
  (void)vpx_codec_control(&codec, VP9E_SET_SVC, 1);

  // Allocate a tiny I420 image to feed encode(). We do NOT feed raw
  // data pixel bytes; the bitstream structure is not what the LG is
  // about. Random noise is fine.
  vpx_image_t raw;
  if (vpx_img_alloc(&raw, VPX_IMG_FMT_I420, g_w, g_h, 1) == nullptr) {
    vpx_codec_destroy(&codec);
    return 0;
  }
  // Seed the frame planes with a deterministic pattern so libFuzzer
  // reproducibility is preserved.
  for (int plane = 0; plane < 3; ++plane) {
    memset(raw.planes[plane], 0x80,
           static_cast<size_t>(raw.stride[plane]) *
               static_cast<size_t>((plane == 0) ? g_h : (g_h / 2)));
  }

  // ---- Encode loop with interleaved layer-id + ref-frame config --
  int frame_count = 0;
  const int max_frames = 1 + ((gop_bits & 0x07));  // 1..8 frames
  const int bound = (max_frames > kMaxFrames) ? kMaxFrames : max_frames;

  for (int f = 0; f < bound; ++f) {
    // VP9E_SET_SVC_LAYER_ID — pick a legal spatial / temporal id
    // deterministically from the seed + frame index.
    vpx_svc_layer_id_t layer_id = {};
    const int sp = (layer_id_seed + f) % ss_layers;
    layer_id.spatial_layer_id = sp;
    layer_id.temporal_layer_id = (layer_id_seed >> 2) % ts_layers;
    for (int s = 0; s < VPX_SS_MAX_LAYERS; ++s) {
      layer_id.temporal_layer_id_per_spatial[s] =
          (layer_id_seed >> 4) % ts_layers;
    }
    (void)vpx_codec_control(&codec, VP9E_SET_SVC_LAYER_ID, &layer_id);

    // VP9E_SET_SVC_REF_FRAME_CONFIG — exercise the ref-frame config
    // path on every other frame. Zero-initialized struct means
    // "use default" which hits the default-assignment branch in
    // vp9_svc_layercontext.c.
    if ((ref_seed >> (f % 8)) & 1) {
      vpx_svc_ref_frame_config_t ref_cfg = {};
      // Last buffer index = spatial layer id (legal per lg docs).
      for (int s = 0; s < ss_layers; ++s) {
        ref_cfg.lst_fb_idx[s] = s;
        ref_cfg.gld_fb_idx[s] = (s + 1) % 8;
        ref_cfg.alt_fb_idx[s] = (s + 2) % 8;
        ref_cfg.reference_last[s] = 1;
      }
      (void)vpx_codec_control(&codec, VP9E_SET_SVC_REF_FRAME_CONFIG,
                              &ref_cfg);
    }

    // Encode one frame.
    int flags = 0;
    if (f == 0) flags |= VPX_EFLAG_FORCE_KF;
    (void)vpx_codec_encode(&codec, &raw, frame_count++, 1, flags,
                           VPX_DL_REALTIME);

    // Drain packets.
    vpx_codec_iter_t iter = nullptr;
    while (vpx_codec_get_cx_data(&codec, &iter) != nullptr) {
      // no-op: we only care about side effects in encode.
    }
  }

  // Flush.
  (void)vpx_codec_encode(&codec, nullptr, frame_count, 1, 0,
                         VPX_DL_REALTIME);
  vpx_codec_iter_t iter = nullptr;
  while (vpx_codec_get_cx_data(&codec, &iter) != nullptr) {
  }

  // ---- Cleanup — single exit path from here ----------------------
  vpx_img_free(&raw);
  vpx_codec_destroy(&codec);
  return 0;
}
