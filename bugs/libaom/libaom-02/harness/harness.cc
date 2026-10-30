#include <fuzzer/FuzzedDataProvider.h>

#include <cstddef>
#include <cstdint>
#include <memory>

#include "av1/ratectrl_rtc.h"

namespace {

// Clamps that keep the object creation path alive. These match the
// ranges libaom's own av1_ratectrl_rtc_init_ratecontrol_config default
// produces, so Create() succeeds and the fuzzer actually reaches the
// downstream rate-control math.
constexpr int kMinDim = 64;
constexpr int kMaxDim = 1920;
constexpr int kMaxSSLayers = 4;   // kAomAV1MaxSpatialLayers
constexpr int kMaxTSLayers = 8;   // kAomAV1MaxTemporalLayers
constexpr int kMaxLayers = 32;    // kAomAV1MaxLayers

void FillCfg(aom::AV1RateControlRtcConfig* cfg, FuzzedDataProvider* fdp) {
  cfg->width = fdp->ConsumeIntegralInRange<int>(kMinDim, kMaxDim);
  cfg->height = fdp->ConsumeIntegralInRange<int>(kMinDim, kMaxDim);
  cfg->is_screen = fdp->ConsumeBool();

  // Quantizer bounds — keep min <= max. 0..63 is the legal range.
  cfg->min_quantizer = fdp->ConsumeIntegralInRange<int>(0, 63);
  cfg->max_quantizer =
      fdp->ConsumeIntegralInRange<int>(cfg->min_quantizer, 63);

  // Bandwidth: keep > 0. A zero here produces a divide-by-zero in
  // av1_rc_regulate_q; that bug class is (a) already well-known and
  // (b) a harness-author-error for this interface per the ratectrl_rtc
  // documentation (it says target_bandwidth must be positive). Fuzz

  // matter for real WebRTC traffic.
  cfg->target_bandwidth =
      fdp->ConsumeIntegralInRange<int64_t>(1, 100'000'000);

  // Buffer sizes — keep the inequality buf_initial <= buf_optimal <=
  // buf_sz so InitRateControl doesn't abort on its own sanity checks.
  cfg->buf_sz = fdp->ConsumeIntegralInRange<int64_t>(1000, 20'000);
  cfg->buf_optimal_sz =
      fdp->ConsumeIntegralInRange<int64_t>(100, cfg->buf_sz);
  cfg->buf_initial_sz =
      fdp->ConsumeIntegralInRange<int64_t>(100, cfg->buf_optimal_sz);

  cfg->undershoot_pct = fdp->ConsumeIntegralInRange<int>(0, 100);
  cfg->overshoot_pct = fdp->ConsumeIntegralInRange<int>(0, 100);
  cfg->max_intra_bitrate_pct = fdp->ConsumeIntegralInRange<int>(0, 1000);
  cfg->max_inter_bitrate_pct = fdp->ConsumeIntegralInRange<int>(0, 1000);
  cfg->frame_drop_thresh = fdp->ConsumeIntegralInRange<int>(0, 100);
  cfg->max_consec_drop_ms = fdp->ConsumeIntegralInRange<int>(0, 5000);
  cfg->framerate = static_cast<double>(
      fdp->ConsumeIntegralInRange<int>(1, 120));
  cfg->aq_mode = fdp->ConsumeIntegralInRange<int>(0, 3);

  // Layer counts — clamp so ss*ts <= kMaxLayers (32).
  cfg->ss_number_layers = fdp->ConsumeIntegralInRange<int>(1, kMaxSSLayers);
  cfg->ts_number_layers = fdp->ConsumeIntegralInRange<int>(1, kMaxTSLayers);
  if (cfg->ss_number_layers * cfg->ts_number_layers > kMaxLayers) {
    cfg->ts_number_layers = kMaxLayers / cfg->ss_number_layers;
    if (cfg->ts_number_layers < 1) cfg->ts_number_layers = 1;
  }

  // Scaling factors per spatial layer. Must be num<=den and den!=0.
  for (int s = 0; s < kMaxSSLayers; ++s) {
    const int den = fdp->ConsumeIntegralInRange<int>(1, 4);
    const int num = fdp->ConsumeIntegralInRange<int>(1, den);
    cfg->scaling_factor_num[s] = num;
    cfg->scaling_factor_den[s] = den;
  }

  // ts_rate_decimator per temporal layer. Standard WebRTC pattern is
  // {4,2,1} or {2,1} or {1}. Keep >0.
  for (int t = 0; t < kMaxTSLayers; ++t) {
    cfg->ts_rate_decimator[t] =
        fdp->ConsumeIntegralInRange<int>(1, 8);
  }

  // Per-layer bitrate and quantizer arrays.
  for (int i = 0; i < kMaxLayers; ++i) {
    cfg->layer_target_bitrate[i] =
        fdp->ConsumeIntegralInRange<int>(1, 10000);
    cfg->min_quantizers[i] = fdp->ConsumeIntegralInRange<int>(0, 63);
    cfg->max_quantizers[i] =
        fdp->ConsumeIntegralInRange<int>(cfg->min_quantizers[i], 63);
  }
}

}  // namespace

extern "C" int LLVMFuzzerTestOneInput(const uint8_t* data, size_t size) {
  if (size < 32) return 0;

  FuzzedDataProvider fdp(data, size);

  // Start from the library-provided default. That gives us every
  // default-initialized field that AV1RateControlRtcConfig's
  // constructor sets, so mutations stay in a Create()-compatible
  // shape.
  aom::AV1RateControlRtcConfig cfg;
  FillCfg(&cfg, &fdp);

  std::unique_ptr<aom::AV1RateControlRTC> rc =
      aom::AV1RateControlRTC::Create(cfg);
  if (!rc) {
    // Create() rejected the config — that's the good path, libaom
    // caught the bad input before allocating downstream state. No
    // cleanup needed: unique_ptr is empty.
    return 0;
  }

  // Drive a short sequence of Update/ComputeQP/PostEncodeUpdate
  // calls. Bound loop counts so each LLVMFuzzerTestOneInput stays
  // fast.
  const int rounds = fdp.ConsumeIntegralInRange<int>(1, 6);
  for (int r = 0; r < rounds && fdp.remaining_bytes() >= 8; ++r) {
    // Optional: push a fresh cfg via UpdateRateControl. This is the
    // primary mutation point real WebRTC hits at runtime.
    if (fdp.ConsumeBool()) {
      aom::AV1RateControlRtcConfig new_cfg;
      FillCfg(&new_cfg, &fdp);
      (void)rc->UpdateRateControl(new_cfg);
    }

    aom::AV1FrameParamsRTC frame_params;
    frame_params.frame_type =
        (r == 0 || fdp.ConsumeBool()) ? aom::kKeyFrame : aom::kInterFrame;
    frame_params.spatial_layer_id =
        fdp.ConsumeIntegralInRange<int>(0, cfg.ss_number_layers - 1);
    frame_params.temporal_layer_id =
        fdp.ConsumeIntegralInRange<int>(0, cfg.ts_number_layers - 1);

    const aom::FrameDropDecision decision = rc->ComputeQP(frame_params);
    if (decision == aom::kFrameDropDecisionDrop) {
      // Per header contract: on Drop we must NOT call GetQP /
      // PostEncodeUpdate for this frame.
      continue;
    }

    (void)rc->GetQP();
    (void)rc->GetLoopfilterLevel();
    (void)rc->GetCdefInfo();
    aom::AV1SegmentationData seg;
    (void)rc->GetSegmentationData(&seg);

    const uint64_t encoded_size =
        fdp.ConsumeIntegralInRange<uint64_t>(1, 200000);
    rc->PostEncodeUpdate(encoded_size);
  }

  // unique_ptr<rc> destruction runs the dtor on every exit path.
  return 0;
}
