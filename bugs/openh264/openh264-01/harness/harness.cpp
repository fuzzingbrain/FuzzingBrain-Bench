#include <stddef.h>
#include <stdint.h>
#include <string.h>
#include <new>

#include "IWelsVP.h"

// Valid processing method types to test
static const EMethods kMethodTypes[] = {
  METHOD_DENOISE,
  METHOD_DOWNSAMPLE,
  METHOD_SCENE_CHANGE_DETECTION_VIDEO,
  METHOD_BACKGROUND_DETECTION,
  METHOD_IMAGE_ROTATE,
  METHOD_SCROLL_DETECTION,
};
static const int kNumMethods = sizeof(kMethodTypes) / sizeof(kMethodTypes[0]);

// Size constraints
static const int kMinWidth = 16;
static const int kMaxWidth = 640;
static const int kMinHeight = 16;
static const int kMaxHeight = 480;

// Align to 16 for SIMD operations
static inline int Align16(int value) {
  return (value + 15) & ~15;
}

static inline int Clamp(int value, int min_val, int max_val) {
  if (value < min_val) return min_val;
  if (value > max_val) return max_val;
  return value;
}

extern "C" int LLVMFuzzerTestOneInput(const uint8_t* data, size_t size) {
  // Need at least 5 bytes: 1 for method, 2 for width, 2 for height
  if (size < 5) {
    return 0;
  }

  // Extract parameters from fuzz input
  int methodIdx = data[0] % kNumMethods;
  EMethods method = kMethodTypes[methodIdx];

  int srcWidth = ((data[1] << 8) | data[2]) % (kMaxWidth - kMinWidth + 1) + kMinWidth;
  int srcHeight = ((data[3] << 8) | data[4]) % (kMaxHeight - kMinHeight + 1) + kMinHeight;

  // Align dimensions
  srcWidth = Align16(srcWidth);
  srcHeight = Align16(srcHeight);
  srcWidth = Clamp(srcWidth, kMinWidth, kMaxWidth);
  srcHeight = Clamp(srcHeight, kMinHeight, kMaxHeight);

  // For downsample, destination is half the size
  int dstWidth = srcWidth / 2;
  int dstHeight = srcHeight / 2;
  if (dstWidth < kMinWidth) dstWidth = kMinWidth;
  if (dstHeight < kMinHeight) dstHeight = kMinHeight;

  // Skip header bytes
  const uint8_t* imageData = data + 5;
  size_t imageDataSize = size - 5;

  // Create video processor interface
  IWelsVP* vp = nullptr;
  EResult ret = WelsCreateVpInterface((void**)&vp, WELSVP_INTERFACE_VERION);
  if (ret != RET_SUCCESS || vp == nullptr) {
    return 0;
  }

  // Initialize the specific method
  ret = vp->Init(method, nullptr);
  if (ret != RET_SUCCESS) {
    WelsDestroyVpInterface(vp, WELSVP_INTERFACE_VERION);
    return 0;
  }

  // Calculate buffer sizes for I420 format
  size_t srcYSize = (size_t)srcWidth * srcHeight;
  size_t srcUVSize = srcYSize / 4;
  size_t srcTotalSize = srcYSize + srcUVSize * 2;

  size_t dstYSize = (size_t)dstWidth * dstHeight;
  size_t dstUVSize = dstYSize / 4;
  size_t dstTotalSize = dstYSize + dstUVSize * 2;

  // Calculate macroblock count for BACKGROUND_DETECTION
  int mbWidth = (srcWidth + 15) >> 4;
  int mbHeight = (srcHeight + 15) >> 4;
  int numMb = mbWidth * mbHeight;

  // Allocate source buffer
  uint8_t* srcBuffer = new (std::nothrow) uint8_t[srcTotalSize];
  if (srcBuffer == nullptr) {
    vp->Uninit(method);
    WelsDestroyVpInterface(vp, WELSVP_INTERFACE_VERION);
    return 0;
  }

  // Fill source buffer with fuzz data
  if (imageDataSize >= srcTotalSize) {
    memcpy(srcBuffer, imageData, srcTotalSize);
  } else {
    memcpy(srcBuffer, imageData, imageDataSize);
    memset(srcBuffer + imageDataSize, 128, srcTotalSize - imageDataSize);
  }

  // Allocate destination buffer
  uint8_t* dstBuffer = new (std::nothrow) uint8_t[dstTotalSize];
  if (dstBuffer == nullptr) {
    delete[] srcBuffer;
    vp->Uninit(method);
    WelsDestroyVpInterface(vp, WELSVP_INTERFACE_VERION);
    return 0;
  }
  memset(dstBuffer, 0, dstTotalSize);

  // For BACKGROUND_DETECTION, we need to call Set() with proper structures
  // This follows the correct API usage pattern (Principle 2)
  SVAACalcResult vaaCalcResult;
  SBGDInterface bgdInterface;
  int8_t* pBackgroundMbFlag = nullptr;
  int (*pSad8x8)[4] = nullptr;
  int* pSsd16x16 = nullptr;
  int* pSum16x16 = nullptr;
  int* pSumOfSquare16x16 = nullptr;
  int (*pSumOfDiff8x8)[4] = nullptr;
  uint8_t (*pMad8x8)[4] = nullptr;

  if (method == METHOD_BACKGROUND_DETECTION) {
    // Allocate arrays for SVAACalcResult
    pSad8x8 = new (std::nothrow) int[numMb][4];
    pSsd16x16 = new (std::nothrow) int[numMb];
    pSum16x16 = new (std::nothrow) int[numMb];
    pSumOfSquare16x16 = new (std::nothrow) int[numMb];
    pSumOfDiff8x8 = new (std::nothrow) int[numMb][4];
    pMad8x8 = new (std::nothrow) uint8_t[numMb][4];
    pBackgroundMbFlag = new (std::nothrow) int8_t[numMb];

    if (!pSad8x8 || !pSsd16x16 || !pSum16x16 || !pSumOfSquare16x16 ||
        !pSumOfDiff8x8 || !pMad8x8 || !pBackgroundMbFlag) {
      // Cleanup on allocation failure
      delete[] pSad8x8;
      delete[] pSsd16x16;
      delete[] pSum16x16;
      delete[] pSumOfSquare16x16;
      delete[] pSumOfDiff8x8;
      delete[] pMad8x8;
      delete[] pBackgroundMbFlag;
      delete[] srcBuffer;
      delete[] dstBuffer;
      vp->Uninit(method);
      WelsDestroyVpInterface(vp, WELSVP_INTERFACE_VERION);
      return 0;
    }

    // Initialize arrays with fuzz-derived or default values
    memset(pBackgroundMbFlag, 0, numMb * sizeof(int8_t));
    memset(pSsd16x16, 0, numMb * sizeof(int));
    memset(pSum16x16, 0, numMb * sizeof(int));
    memset(pSumOfSquare16x16, 0, numMb * sizeof(int));
    for (int i = 0; i < numMb; i++) {
      for (int j = 0; j < 4; j++) {
        pSad8x8[i][j] = 0;
        pSumOfDiff8x8[i][j] = 0;
        pMad8x8[i][j] = 0;
      }
    }

    // Setup SVAACalcResult
    memset(&vaaCalcResult, 0, sizeof(SVAACalcResult));
    vaaCalcResult.pCurY = srcBuffer;
    vaaCalcResult.pRefY = srcBuffer;  // Use same buffer as reference for simplicity
    vaaCalcResult.pSad8x8 = pSad8x8;
    vaaCalcResult.pSsd16x16 = pSsd16x16;
    vaaCalcResult.pSum16x16 = pSum16x16;
    vaaCalcResult.pSumOfSquare16x16 = pSumOfSquare16x16;
    vaaCalcResult.pSumOfDiff8x8 = pSumOfDiff8x8;
    vaaCalcResult.pMad8x8 = pMad8x8;
    vaaCalcResult.iFrameSad = 0;

    // Setup SBGDInterface
    bgdInterface.pBackgroundMbFlag = pBackgroundMbFlag;
    bgdInterface.pCalcRes = &vaaCalcResult;

    // Call Set() to initialize the background detection parameters
    // This is required before calling Process() for BACKGROUND_DETECTION
    ret = vp->Set(method, &bgdInterface);
    if (ret != RET_SUCCESS) {
      delete[] pSad8x8;
      delete[] pSsd16x16;
      delete[] pSum16x16;
      delete[] pSumOfSquare16x16;
      delete[] pSumOfDiff8x8;
      delete[] pMad8x8;
      delete[] pBackgroundMbFlag;
      delete[] srcBuffer;
      delete[] dstBuffer;
      vp->Uninit(method);
      WelsDestroyVpInterface(vp, WELSVP_INTERFACE_VERION);
      return 0;
    }
  }

  // Setup source SPixMap
  SPixMap srcPixMap;
  memset(&srcPixMap, 0, sizeof(SPixMap));
  srcPixMap.pPixel[0] = srcBuffer;                           // Y plane
  srcPixMap.pPixel[1] = srcBuffer + srcYSize;                // U plane
  srcPixMap.pPixel[2] = srcBuffer + srcYSize + srcUVSize;    // V plane
  srcPixMap.iStride[0] = srcWidth;
  srcPixMap.iStride[1] = srcWidth / 2;
  srcPixMap.iStride[2] = srcWidth / 2;
  srcPixMap.sRect.iRectTop = 0;
  srcPixMap.sRect.iRectLeft = 0;
  srcPixMap.sRect.iRectWidth = srcWidth;
  srcPixMap.sRect.iRectHeight = srcHeight;
  srcPixMap.eFormat = VIDEO_FORMAT_I420;

  // Setup destination SPixMap
  SPixMap dstPixMap;
  memset(&dstPixMap, 0, sizeof(SPixMap));
  dstPixMap.pPixel[0] = dstBuffer;
  dstPixMap.pPixel[1] = dstBuffer + dstYSize;
  dstPixMap.pPixel[2] = dstBuffer + dstYSize + dstUVSize;
  dstPixMap.iStride[0] = dstWidth;
  dstPixMap.iStride[1] = dstWidth / 2;
  dstPixMap.iStride[2] = dstWidth / 2;
  dstPixMap.sRect.iRectTop = 0;
  dstPixMap.sRect.iRectLeft = 0;
  dstPixMap.sRect.iRectWidth = dstWidth;
  dstPixMap.sRect.iRectHeight = dstHeight;
  dstPixMap.eFormat = VIDEO_FORMAT_I420;

  // Process the image
  vp->Process(method, &srcPixMap, &dstPixMap);

  // Cleanup
  if (method == METHOD_BACKGROUND_DETECTION) {
    delete[] pSad8x8;
    delete[] pSsd16x16;
    delete[] pSum16x16;
    delete[] pSumOfSquare16x16;
    delete[] pSumOfDiff8x8;
    delete[] pMad8x8;
    delete[] pBackgroundMbFlag;
  }
  delete[] srcBuffer;
  delete[] dstBuffer;
  vp->Uninit(method);
  WelsDestroyVpInterface(vp, WELSVP_INTERFACE_VERION);

  return 0;
}
