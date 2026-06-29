#include <fuzzer/FuzzedDataProvider.h>

#include <cstddef>
#include <cstdint>
#include <cstring>

#include "aom/aom_codec.h"
#include "aom/aom_encoder.h"
#include "aom/aom_image.h"
#include "aom/aomcx.h"

namespace {

constexpr unsigned int kMinDim = 64;
constexpr unsigned int kMaxDim = 256;

// Clamp helpers for the SVC layer counts per aomcx.h.
constexpr int kMaxSSLayers = AOM_MAX_SS_LAYERS;  // 4
constexpr int kMaxTSLayers = AOM_MAX_TS_LAYERS;  // 8
constexpr int kMaxLayers = AOM_MAX_LAYERS;       // 32

void FillSvcParams(aom_svc_params_t* svc, FuzzedDataProvider* fdp) {
  std::memset(svc, 0, sizeof(*svc));

  // Spatial layers: [1..AOM_MAX_SS_LAYERS].
  svc->number_spatial_layers =
      fdp->ConsumeIntegralInRange<int>(1, kMaxSSLayers);
  // Temporal layers: [1..AOM_MAX_TS_LAYERS].
  svc->number_temporal_layers =
      fdp->ConsumeIntegralInRange<int>(1, kMaxTSLayers);

  // Enforce total <= AOM_MAX_LAYERS. Max is already 4*8=32, so the
  // product is always within bounds, but we still defensively clamp in

  if (svc->number_spatial_layers * svc->number_temporal_layers >
      kMaxLayers) {
    svc->number_temporal_layers = kMaxLayers / svc->number_spatial_layers;
    if (svc->number_temporal_layers < 1) svc->number_temporal_layers = 1;
  }

  // Scaling factors per spatial layer: standard WebRTC ladder
  // {1/4, 1/2, 1} or {1/2, 1} or {1}. Populate from fuzz-picked
  // valid pairs; a /0 would be a harness bug (P1), not a libaom bug.
  for (int s = 0; s < kMaxSSLayers; ++s) {
    switch (fdp->ConsumeIntegralInRange<int>(0, 3)) {
      case 0:
        svc->scaling_factor_num[s] = 1;
        svc->scaling_factor_den[s] = 4;
        break;
      case 1:
        svc->scaling_factor_num[s] = 1;
        svc->scaling_factor_den[s] = 2;
        break;
      case 2:
        svc->scaling_factor_num[s] = 3;
        svc->scaling_factor_den[s] = 4;
        break;
      default:
        svc->scaling_factor_num[s] = 1;
        svc->scaling_factor_den[s] = 1;
        break;
    }
  }

  // Framerate factor per temporal layer: standard libaom pattern is
  // {4,2,1} for 3 TS layers, {2,1} for 2, {1} for 1. Pick from a
  // fuzz-driven set of non-zero values.
  for (int t = 0; t < kMaxTSLayers; ++t) {
    svc->framerate_factor[t] =
        fdp->ConsumeIntegralInRange<int>(1, 8);
  }

  // Per-layer quantizer and bitrate. Keep within 0..63 / 0..10_000
  // (kbps) so the rate-controller can reason about them without

  for (int i = 0; i < kMaxLayers; ++i) {
    svc->min_quantizers[i] = fdp->ConsumeIntegralInRange<int>(0, 63);
    svc->max_quantizers[i] =
        fdp->ConsumeIntegralInRange<int>(svc->min_quantizers[i], 63);
    svc->layer_target_bitrate[i] =
        fdp->ConsumeIntegralInRange<int>(1, 10000);
  }
}

}  // namespace

extern "C" int LLVMFuzzerTestOneInput(const uint8_t* data, size_t size) {
  if (size < 32) return 0;

  FuzzedDataProvider fdp(data, size);

  aom_codec_iface_t* iface = aom_codec_av1_cx();
  if (iface == nullptr) return 0;

  aom_codec_enc_cfg_t cfg;
  std::memset(&cfg, 0, sizeof(cfg));
  if (aom_codec_enc_config_default(iface, &cfg, AOM_USAGE_REALTIME) !=
      AOM_CODEC_OK) {
    return 0;
  }

  unsigned int width = fdp.ConsumeIntegralInRange<unsigned int>(kMinDim, kMaxDim);
  unsigned int height = fdp.ConsumeIntegralInRange<unsigned int>(kMinDim, kMaxDim);
  width &= ~1u;
  height &= ~1u;
  if (width < kMinDim) width = kMinDim;
  if (height < kMinDim) height = kMinDim;

  cfg.g_w = width;
  cfg.g_h = height;
  cfg.g_timebase.num = 1;
  cfg.g_timebase.den = 30;
  cfg.g_threads = 1;
  cfg.g_lag_in_frames = 0;
  cfg.rc_end_usage = AOM_CBR;
  cfg.rc_target_bitrate = 400;
  cfg.kf_mode = AOM_KF_AUTO;
  cfg.kf_max_dist = 9999;
  cfg.g_error_resilient = 0;

  aom_codec_ctx_t ctx;
  std::memset(&ctx, 0, sizeof(ctx));
  if (aom_codec_enc_init_ver(&ctx, iface, &cfg, 0,
                             AOM_ENCODER_ABI_VERSION) != AOM_CODEC_OK) {
    return 0;
  }

  // Keep speed fast. AOME_SET_CPUUSED for usage=REALTIME is [5..10].
  aom_codec_control(&ctx, AOME_SET_CPUUSED, 9);

  // --- Step 1: push the SVC params. ---
  aom_svc_params_t svc;
  FillSvcParams(&svc, &fdp);
  (void)aom_codec_control(&ctx, AV1E_SET_SVC_PARAMS, &svc);

  // --- Step 2: allocate one raw image and encode N layered frames. ---
  aom_image_t img;
  std::memset(&img, 0, sizeof(img));
  if (aom_img_alloc(&img, AOM_IMG_FMT_I420, width, height, 1) == nullptr) {
    aom_codec_destroy(&ctx);
    return 0;
  }
  // Zero the planes — we are testing layer-context state machines,
  // not residue encoding. Deterministic constant input is fine.
  for (int p = 0; p < 3; ++p) {
    if (img.planes[p] == nullptr) continue;
    unsigned int plane_h = img.d_h;
    unsigned int plane_w = img.d_w;
    if (p != 0) {
      if (img.y_chroma_shift) plane_h >>= img.y_chroma_shift;
      if (img.x_chroma_shift) plane_w >>= img.x_chroma_shift;
      if (plane_h == 0) plane_h = 1;
      if (plane_w == 0) plane_w = 1;
    }
    for (unsigned int y = 0; y < plane_h; ++y) {
      std::memset(img.planes[p] + y * img.stride[p], 0x80, plane_w);
    }
  }

  const int frames = fdp.ConsumeIntegralInRange<int>(1, 6);
  for (int i = 0; i < frames && fdp.remaining_bytes() >= 8; ++i) {
    aom_svc_layer_id_t layer_id;
    layer_id.spatial_layer_id =
        fdp.ConsumeIntegralInRange<int>(0, svc.number_spatial_layers - 1);
    layer_id.temporal_layer_id =
        fdp.ConsumeIntegralInRange<int>(0, svc.number_temporal_layers - 1);
    (void)aom_codec_control(&ctx, AV1E_SET_SVC_LAYER_ID, &layer_id);

    // Optional ref-frame config — only when the fuzz bytes say so.
    // The reference/ref_idx/refresh arrays must stay within documented
    // ranges per aomcx.h; we clamp hard here.
    if (fdp.ConsumeBool()) {
      aom_svc_ref_frame_config_t ref_cfg;
      std::memset(&ref_cfg, 0, sizeof(ref_cfg));
      for (int r = 0; r < 7; ++r) {
        ref_cfg.reference[r] = fdp.ConsumeBool() ? 1 : 0;
        ref_cfg.ref_idx[r] = fdp.ConsumeIntegralInRange<int>(0, 7);
      }
      for (int r = 0; r < 8; ++r) {
        ref_cfg.refresh[r] = fdp.ConsumeBool() ? 1 : 0;
      }
      (void)aom_codec_control(
          &ctx, AV1E_SET_SVC_REF_FRAME_CONFIG, &ref_cfg);
    }

    const int64_t pts = static_cast<int64_t>(i);
    const unsigned long duration = 1;
    aom_enc_frame_flags_t flags = 0;
    if (i == 0) flags |= AOM_EFLAG_FORCE_KF;
    (void)aom_codec_encode(&ctx, &img, pts, duration, flags);

    aom_codec_iter_t iter = nullptr;
    while (aom_codec_get_cx_data(&ctx, &iter) != nullptr) {
      // drain
    }
  }

  // Flush.
  for (int guard = 0; guard < 4; ++guard) {
    if (aom_codec_encode(&ctx, nullptr, -1, 0, 0) != AOM_CODEC_OK) break;
    aom_codec_iter_t iter = nullptr;
    bool drained = false;
    while (aom_codec_get_cx_data(&ctx, &iter) != nullptr) drained = true;
    if (!drained) break;
  }

  aom_img_free(&img);
  aom_codec_destroy(&ctx);
  return 0;
}
