// libFuzzer harness for libsharpyuv SharpYuvConvert (gamma-LUT OOB).
// Public API only (sharpyuv/sharpyuv.h). Adapted from the public-API
// reproduction repro_sharpyuv.cpp.
//
// Input layout (matches the reference repro):
//   [0..1] width seed (LE u16)   -> width  = (raw % 128) + 1
//   [2..3] height seed (LE u16)  -> height = (raw % 128) + 1
//   [4]    rgb_bit_depth select  -> {8,10,12,16}[sel % 4]
//   [5]    yuv_bit_depth select  -> {8,10,12}[sel % 3]
//   [6..7] reserved
//   [8..]  raw RGB pixel bytes copied into the RGB plane

#include <cstdint>
#include <cstddef>
#include <cstring>
#include <vector>

#include "sharpyuv/sharpyuv.h"
#include "sharpyuv/sharpyuv_csp.h"

extern "C" int LLVMFuzzerTestOneInput(const uint8_t* data, size_t size) {
  if (size < 8) return 0;

  uint16_t w_raw = static_cast<uint16_t>(data[0] | (data[1] << 8));
  uint16_t h_raw = static_cast<uint16_t>(data[2] | (data[3] << 8));
  uint8_t rgb_bd_sel = data[4];
  uint8_t yuv_bd_sel = data[5];

  int width = (w_raw % 128) + 1;
  int height = (h_raw % 128) + 1;
  static const int kRgbBitDepths[] = {8, 10, 12, 16};
  static const int kYuvBitDepths[] = {8, 10, 12};
  int rgb_bit_depth = kRgbBitDepths[rgb_bd_sel % 4];
  int yuv_bit_depth = kYuvBitDepths[yuv_bd_sel % 3];

  int rgb_bps = (rgb_bit_depth > 8) ? 2 : 1;
  int yuv_bps = (yuv_bit_depth > 8) ? 2 : 1;
  int rgb_step = 3 * rgb_bps;
  int rgb_stride = width * rgb_step;
  size_t rgb_size = static_cast<size_t>(rgb_stride) * height;

  std::vector<uint8_t> rgb_buf(rgb_size, 0);
  size_t pixel_data_size = size - 8;
  size_t copy_len = (pixel_data_size < rgb_size) ? pixel_data_size : rgb_size;
  memcpy(rgb_buf.data(), data + 8, copy_len);

  int uv_width = (width + 1) / 2;
  int uv_height = (height + 1) / 2;
  int y_stride = width * yuv_bps;
  int u_stride = uv_width * yuv_bps;
  int v_stride = uv_width * yuv_bps;

  std::vector<uint8_t> y_buf(static_cast<size_t>(y_stride) * height, 0);
  std::vector<uint8_t> u_buf(static_cast<size_t>(u_stride) * uv_height, 0);
  std::vector<uint8_t> v_buf(static_cast<size_t>(v_stride) * uv_height, 0);

  SharpYuvColorSpace color_space;
  color_space.kr = 0.2990f;
  color_space.kb = 0.1140f;
  color_space.bit_depth = yuv_bit_depth;
  color_space.range = kSharpYuvRangeFull;

  SharpYuvConversionMatrix matrix;
  SharpYuvComputeConversionMatrix(&color_space, &matrix);

  const void* r_ptr = rgb_buf.data();
  const void* g_ptr = rgb_buf.data() + rgb_bps;
  const void* b_ptr = rgb_buf.data() + 2 * rgb_bps;

  SharpYuvConvert(r_ptr, g_ptr, b_ptr, rgb_step, rgb_stride, rgb_bit_depth,
                  y_buf.data(), y_stride, u_buf.data(), u_stride,
                  v_buf.data(), v_stride, yuv_bit_depth, width, height,
                  &matrix);
  return 0;
}
