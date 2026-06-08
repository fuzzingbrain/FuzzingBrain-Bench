#ifdef UNSAFE_BUFFERS_BUILD
#pragma allow_unsafe_buffers
#endif
/*
 * Copyright 2023 Google Inc.
 *
 * Use of this source code is governed by a BSD-style license that can be
 * found in the LICENSE file.
 */

// libFuzzer harness for Logic Group: skia_image_filter_chain_construction

#include <fuzzer/FuzzedDataProvider.h>

#include <cstddef>
#include <cstdint>
#include <vector>

#include "include/core/SkBitmap.h"
#include "include/core/SkCanvas.h"
#include "include/core/SkColor.h"
#include "include/core/SkImageFilter.h"
#include "include/core/SkPaint.h"
#include "include/core/SkRect.h"
#include "include/core/SkSurface.h"
#include "include/effects/SkImageFilters.h"

namespace {

const size_t kMaxInputSize = 16 * 1024;
const int kMaxChainDepth = 16;
const int kCanvasSize = 64;

sk_sp<SkImageFilter> MakeRandomFilter(FuzzedDataProvider* provider,
                                       int depth) {
  if (depth >= kMaxChainDepth || provider->remaining_bytes() < 4) {
    return nullptr;  // null input = use source image
  }

  uint8_t filter_type = provider->ConsumeIntegral<uint8_t>();

  switch (filter_type % 8) {
    case 0: {
      // Blur
      float sigmaX = provider->ConsumeFloatingPointInRange<float>(0.0f, 100.0f);
      float sigmaY = provider->ConsumeFloatingPointInRange<float>(0.0f, 100.0f);
      return SkImageFilters::Blur(sigmaX, sigmaY,
                                   MakeRandomFilter(provider, depth + 1));
    }
    case 1: {
      // Compose
      auto outer = MakeRandomFilter(provider, depth + 1);
      auto inner = MakeRandomFilter(provider, depth + 1);
      return SkImageFilters::Compose(std::move(outer), std::move(inner));
    }
    case 2: {
      // Offset
      float dx = provider->ConsumeFloatingPointInRange<float>(-100.0f, 100.0f);
      float dy = provider->ConsumeFloatingPointInRange<float>(-100.0f, 100.0f);
      return SkImageFilters::Offset(dx, dy,
                                     MakeRandomFilter(provider, depth + 1));
    }
    case 3: {
      // DropShadow
      float dx = provider->ConsumeFloatingPointInRange<float>(-50.0f, 50.0f);
      float dy = provider->ConsumeFloatingPointInRange<float>(-50.0f, 50.0f);
      float sigmaX = provider->ConsumeFloatingPointInRange<float>(0.0f, 50.0f);
      float sigmaY = provider->ConsumeFloatingPointInRange<float>(0.0f, 50.0f);
      return SkImageFilters::DropShadow(
          dx, dy, sigmaX, sigmaY, SK_ColorBLACK,
          MakeRandomFilter(provider, depth + 1));
    }
    case 4: {
      // Crop
      float l = provider->ConsumeFloatingPointInRange<float>(-100.0f, 100.0f);
      float t = provider->ConsumeFloatingPointInRange<float>(-100.0f, 100.0f);
      float r = provider->ConsumeFloatingPointInRange<float>(-100.0f, 100.0f);
      float b = provider->ConsumeFloatingPointInRange<float>(-100.0f, 100.0f);
      return SkImageFilters::Crop(SkRect::MakeLTRB(l, t, r, b),
                                   MakeRandomFilter(provider, depth + 1));
    }
    case 5: {
      // Merge (2 inputs)
      auto first = MakeRandomFilter(provider, depth + 1);
      auto second = MakeRandomFilter(provider, depth + 1);
      sk_sp<SkImageFilter> inputs[] = {std::move(first), std::move(second)};
      return SkImageFilters::Merge(inputs, 2);
    }
    case 6: {
      // MatrixTransform
      SkMatrix matrix;
      float values[9];
      for (int i = 0; i < 9; i++) {
        values[i] = provider->ConsumeFloatingPointInRange<float>(-10.0f, 10.0f);
      }
      matrix.set9(values);
      return SkImageFilters::MatrixTransform(
          matrix, SkSamplingOptions(),
          MakeRandomFilter(provider, depth + 1));
    }
    case 7: {
      // Empty (null filter)
      return SkImageFilters::Empty();
    }
  }
  return nullptr;
}

}  // namespace

extern "C" int LLVMFuzzerTestOneInput(const uint8_t* data, size_t size) {
  if (size > kMaxInputSize || size < 4) {
    return 0;
  }

  FuzzedDataProvider provider(data, size);

  // Build a fuzz-driven filter chain
  auto filter = MakeRandomFilter(&provider, 0);

  if (filter) {
    // Apply the filter to a small canvas to exercise the render path
    auto surface = SkSurfaces::Raster(
        SkImageInfo::MakeN32Premul(kCanvasSize, kCanvasSize));
    if (surface) {
      SkCanvas* canvas = surface->getCanvas();
      SkPaint paint;
      paint.setImageFilter(std::move(filter));
      canvas->drawRect(SkRect::MakeWH(kCanvasSize, kCanvasSize), paint);
    }
  }

  return 0;
}
