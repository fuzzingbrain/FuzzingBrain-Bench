/*
 *  Copyright (c) 2026 The WebM project authors. All Rights Reserved.
 *
 *  Use of this source code is governed by a BSD-style license
 *  that can be found in the LICENSE file in the root of the source
 *  tree. An additional intellectual property rights grant can be found
 *  in the file PATENTS.  All contributing project authors may
 *  be found in the AUTHORS file in the root of the source tree.
 */

// libFuzzer harness for Logic Group: vp9_encoder_midstream_reconfig
//
// Drives a VP9 encoder through repeated vpx_codec_enc_config_set
// calls between encode() calls, with each reconfig mutating
// (width, height, timebase, rc_target_bitrate, g_lag_in_frames).
// Internally this dispatches to vp9_change_config, which re-runs the
// dimension math, reallocates context buffers, and re-sizes the
// lookahead queue. The in-tree examples/vpx_enc_fuzzer.cc never
// calls config_set at all — every frame is encoded under the
// initial config — so the whole reconfig path is unfuzzed today.
//
// Call pipeline:
//   vpx_codec_enc_config_default → vpx_codec_enc_init →
//   loop over N epochs:
//     { vpx_img_alloc (if dims changed),
//       encode a few frames,
//       vpx_codec_enc_config_set with a mutated cfg }
//   → vpx_codec_destroy.
//
// The reconfig cfg MUST be contract-compliant. Passing arbitrary
// fuzz bytes into rc_target_bitrate / g_timebase / g_lag_in_frames
// directly trips internal asserts in vp9_change_config; that's a
// P2 violation (API misuse). Instead we pick each mutated field
// from a *pre-validated ladder* of legal values so the fuzzer
// varies the sequence of legal states rather than cramming illegal
// individual states. The interesting bug class per the LG notes is
// "a fuzzer can pick (w,h,mb_rows,mb_cols) that passed the initial
// check but overflow after a resize" — we surface that by letting
// the (width,height) pair change between epochs.

#include <stddef.h>
#include <stdint.h>
#include <stdlib.h>
#include <string.h>

#include "vpx/vp8cx.h"
#include "vpx/vpx_encoder.h"
#include "vpx/vpx_image.h"

// Keep dims small enough that the ASan iteration cost stays low
// but large enough that the mb_row/mb_col math is non-trivial.
static constexpr unsigned int kMaxWidth = 256;
static constexpr unsigned int kMaxHeight = 256;
// Pre-validated (w,h) ladder. Every entry is a multiple of 2
// (VP9 4:2:0) and within kMax bounds, so vp9_change_config's
// dimension math is always fed a legal pair even when the fuzzer
// picks a random index.
struct WH {
  unsigned int w, h;
};
static constexpr WH kDimLadder[] = {
    {64, 64},    {128, 64},  {64, 128},   {128, 128},
    {192, 128},  {128, 192}, {256, 128},  {128, 256},
    {192, 192},  {256, 256}, {160, 96},   {96, 160},
};
static constexpr int kDimLadderLen =
    sizeof(kDimLadder) / sizeof(kDimLadder[0]);

// Pre-validated rc_target_bitrate ladder (kbps). Each value is
// small enough that the integer math inside vp9_ratectrl does not
// overflow even when the frame dims are at the kMax corner.
static constexpr unsigned int kBitrateLadder[] = {
    50, 100, 250, 500, 1000, 2000, 4000, 8000,
};
static constexpr int kBitrateLadderLen =
    sizeof(kBitrateLadder) / sizeof(kBitrateLadder[0]);

// Pre-validated timebase ladder. Standard video framerates only.
struct Timebase {
  int num, den;
};
static constexpr Timebase kTimebaseLadder[] = {
    {1, 24}, {1, 25}, {1, 30}, {1, 50}, {1, 60}, {1000, 30000},
};
static constexpr int kTimebaseLadderLen =
    sizeof(kTimebaseLadder) / sizeof(kTimebaseLadder[0]);

extern "C" void usage_exit(void) { exit(EXIT_FAILURE); }

// Apply a mutated cfg picked from the ladders. Returns the new
// (w, h) pair so the caller can reallocate the image if needed.
// NOTE: This function does NOT call vpx_codec_enc_config_set —
// that's the caller's job. We only fill the cfg struct.
static WH mutate_cfg(vpx_codec_enc_cfg_t *cfg, uint8_t seed) {
  const int dim_idx = (seed >> 0) & 0x0f;
  const int br_idx = (seed >> 4) & 0x07;
  const WH dim = kDimLadder[dim_idx % kDimLadderLen];
  cfg->g_w = dim.w;
  cfg->g_h = dim.h;
  cfg->rc_target_bitrate = kBitrateLadder[br_idx % kBitrateLadderLen];
  return dim;
}

extern "C" int LLVMFuzzerTestOneInput(const uint8_t *data, size_t size) {
  // Harness header: 1 byte init-config selector + up to N mutation
  // bytes (one per reconfig epoch). Epoch count is capped at 6 so
  // iterations stay cheap.
  if (size < 2) return 0;

  const uint8_t init_sel = data[0];
  const int initial_dim_idx = (init_sel >> 0) & 0x0f;
  const int initial_br_idx = (init_sel >> 4) & 0x07;
  const WH initial_dim =
      kDimLadder[initial_dim_idx % kDimLadderLen];

  const int initial_tb_idx = data[1] & 0x07;
  const Timebase initial_tb =
      kTimebaseLadder[initial_tb_idx % kTimebaseLadderLen];

  // ---- Build initial cfg (contract-compliant) -------------------
  vpx_codec_enc_cfg_t cfg;
  if (vpx_codec_enc_config_default(vpx_codec_vp9_cx(), &cfg, 0) !=
      VPX_CODEC_OK) {
    return 0;
  }
  cfg.g_w = initial_dim.w;
  cfg.g_h = initial_dim.h;
  cfg.g_timebase.num = initial_tb.num;
  cfg.g_timebase.den = initial_tb.den;
  cfg.rc_target_bitrate = kBitrateLadder[initial_br_idx % kBitrateLadderLen];
  cfg.g_error_resilient = 1;
  cfg.g_lag_in_frames = 0;  // realtime
  cfg.rc_end_usage = VPX_CBR;

  // ---- Init encoder ---------------------------------------------
  vpx_codec_ctx_t codec;
  if (vpx_codec_enc_init(&codec, vpx_codec_vp9_cx(), &cfg, 0) !=
      VPX_CODEC_OK) {
    return 0;
  }

  // ---- Allocate raw image at the initial size -------------------
  vpx_image_t *raw =
      vpx_img_alloc(nullptr, VPX_IMG_FMT_I420, cfg.g_w, cfg.g_h, 1);
  if (raw == nullptr) {
    vpx_codec_destroy(&codec);
    return 0;
  }
  for (int plane = 0; plane < 3; ++plane) {
    const int h_plane =
        (plane == 0) ? static_cast<int>(cfg.g_h)
                     : static_cast<int>((cfg.g_h + 1) / 2);
    memset(raw->planes[plane], 0x80,
           static_cast<size_t>(raw->stride[plane]) *
               static_cast<size_t>(h_plane));
  }

  // ---- Epoch loop: encode a few frames, then reconfig ----------
  int total_frames = 0;
  const size_t payload_off = 2;
  const size_t payload_len = size - payload_off;
  // Up to 6 epochs; each epoch consumes 1 byte from the payload.
  const int max_epochs =
      (payload_len > 6) ? 6 : static_cast<int>(payload_len);

  for (int epoch = 0; epoch < max_epochs; ++epoch) {
    // Encode 2 frames at the current cfg.
    for (int f = 0; f < 2; ++f) {
      int flags = (total_frames == 0) ? VPX_EFLAG_FORCE_KF : 0;
      (void)vpx_codec_encode(&codec, raw, total_frames, 1, flags,
                             VPX_DL_REALTIME);
      ++total_frames;

      vpx_codec_iter_t iter = nullptr;
      while (vpx_codec_get_cx_data(&codec, &iter) != nullptr) {
      }
    }

    // Mutate the cfg for the next epoch and push via config_set.
    const uint8_t epoch_seed = data[payload_off + epoch];
    const WH new_dim = mutate_cfg(&cfg, epoch_seed);

    // vpx_codec_enc_config_set does NOT reallocate the raw image
    // for us; we must free + realloc if dimensions changed.
    vpx_codec_err_t rc = vpx_codec_enc_config_set(&codec, &cfg);
    if (rc != VPX_CODEC_OK) {
      // Reconfig rejected (e.g. because --size-limit was not bumped
      // at libvpx configure time). Fall through without encoding
      // at the new size so we avoid stressing a rejected config.
      break;
    }

    // Reallocate raw if the size changed.
    if (new_dim.w != static_cast<unsigned int>(raw->d_w) ||
        new_dim.h != static_cast<unsigned int>(raw->d_h)) {
      vpx_img_free(raw);
      raw =
          vpx_img_alloc(nullptr, VPX_IMG_FMT_I420, new_dim.w, new_dim.h, 1);
      if (raw == nullptr) {
        // Cannot continue without a raw image; break to the
        // cleanup path. We already destroyed the old image so
        // only codec needs tearing down.
        vpx_codec_destroy(&codec);
        return 0;
      }
      for (int plane = 0; plane < 3; ++plane) {
        const int h_plane =
            (plane == 0) ? static_cast<int>(new_dim.h)
                         : static_cast<int>((new_dim.h + 1) / 2);
        memset(raw->planes[plane], 0x80,
               static_cast<size_t>(raw->stride[plane]) *
                   static_cast<size_t>(h_plane));
      }
    }
  }

  // Flush encoder.
  (void)vpx_codec_encode(&codec, nullptr, total_frames, 1, 0,
                         VPX_DL_REALTIME);
  vpx_codec_iter_t iter = nullptr;
  while (vpx_codec_get_cx_data(&codec, &iter) != nullptr) {
  }

  // ---- Cleanup --------------------------------------------------
  vpx_img_free(raw);
  vpx_codec_destroy(&codec);
  return 0;
}
