#include "libheif/heif.h"

#include <stdint.h>
#include <stdlib.h>
#include <string.h>

static void transform_image(const heif_image_handle* handle,
                              const uint8_t* params, size_t params_size)
{
  if (!handle || params_size < 4) return;

  int orig_w = heif_image_handle_get_width(handle);
  int orig_h = heif_image_handle_get_height(handle);
  if (orig_w <= 0 || orig_h <= 0) return;

  /* Decode to RGB */
  heif_image* image = nullptr;
  heif_error err = heif_decode_image(handle, &image,
                                      heif_colorspace_RGB,
                                      heif_chroma_interleaved_RGBA,
                                      nullptr);
  if (err.code != heif_error_Ok || !image) {
    heif_image_release(image);
    return;
  }

  int img_w = heif_image_get_primary_width(image);
  int img_h = heif_image_get_primary_height(image);

  /* Exercise color profile accessors */
  heif_color_profile_type prof_type = heif_image_get_color_profile_type(image);
  (void)prof_type;
  size_t prof_size = heif_image_get_raw_color_profile_size(image);
  if (prof_size > 0 && prof_size < 1024 * 1024) {
    uint8_t* prof_data = static_cast<uint8_t*>(malloc(prof_size));
    if (prof_data) {
      heif_image_get_raw_color_profile(image, prof_data);
      free(prof_data);
    }
  }

  /* Also check handle-level color profile */
  heif_color_profile_type handle_prof =
      heif_image_handle_get_color_profile_type(handle);
  (void)handle_prof;
  size_t handle_prof_size =
      heif_image_handle_get_raw_color_profile_size(handle);
  if (handle_prof_size > 0 && handle_prof_size < 1024 * 1024) {
    uint8_t* hpd = static_cast<uint8_t*>(malloc(handle_prof_size));
    if (hpd) {
      heif_image_handle_get_raw_color_profile(handle, hpd);
      free(hpd);
    }
  }

  /* Pixel aspect ratio operations */
  uint32_t par_h = params[0] + 1, par_v = params[1] + 1;
  heif_image_set_pixel_aspect_ratio(image, par_h, par_v);

  uint32_t got_h = 0, got_v = 0;
  heif_image_get_pixel_aspect_ratio(image, &got_h, &got_v);

  /* Try scaling */
  if (img_w > 0 && img_h > 0) {
    int scale_w = (params[2] % 4 + 1) * 16;
    int scale_h = (params[3] % 4 + 1) * 16;

    heif_image* scaled = nullptr;
    err = heif_image_scale_image(image, &scaled, scale_w, scale_h, nullptr);
    if (err.code == heif_error_Ok && scaled) {
      (void)heif_image_get_primary_width(scaled);
      (void)heif_image_get_primary_height(scaled);

      int stride = 0;
      const uint8_t* plane = heif_image_get_plane_readonly(
          scaled, heif_channel_interleaved, &stride);
      (void)plane;

      heif_image_release(scaled);
    }
  }

  /* Try cropping if we have enough params */
  if (params_size >= 8 && img_w > 4 && img_h > 4) {
    int crop_left = params[4] % (img_w / 2);
    int crop_top = params[5] % (img_h / 2);
    int crop_w = (params[6] % (img_w - crop_left - 1)) + 1;
    int crop_h = (params[7] % (img_h - crop_top - 1)) + 1;

    if (crop_w > 0 && crop_h > 0 &&
        crop_left + crop_w <= img_w &&
        crop_top + crop_h <= img_h) {
      heif_error cerr = heif_image_crop(image,
                                          crop_left, crop_w + crop_left - 1,
                                          crop_top, crop_h + crop_top - 1);
      (void)cerr;
    }
  }

  /* Premultiplied alpha operations */
  heif_image_set_premultiplied_alpha(image, 1);
  (void)heif_image_is_premultiplied_alpha(image);
  heif_image_set_premultiplied_alpha(image, 0);

  heif_image_release(image);
}

extern "C" int LLVMFuzzerTestOneInput(const uint8_t* data, size_t size)
{
  if (size < 20) {
    return 0;
  }

  /* Reserve last 8 bytes as transform parameters */
  const uint8_t* params = data + size - 8;
  size_t heif_size = size - 8;

  heif_context* ctx = heif_context_alloc();
  if (!ctx) return 0;

  heif_security_limits* limits = heif_context_get_security_limits(ctx);
  if (limits) {
    limits->max_total_memory = static_cast<uint64_t>(2) * 1024 * 1024 * 1024;
    limits->max_memory_block_size = 128 * 1024 * 1024;
  }
  heif_context_set_max_decoding_threads(ctx, 0);

  heif_error err = heif_context_read_from_memory(ctx, data, heif_size, nullptr);
  if (err.code != heif_error_Ok) {
    heif_context_free(ctx);
    return 0;
  }

  /* Transform primary image */
  heif_image_handle* primary = nullptr;
  err = heif_context_get_primary_image_handle(ctx, &primary);
  if (err.code == heif_error_Ok && primary) {
    /* Get preferred decoding colorspace */
    enum heif_colorspace pref_cs;
    enum heif_chroma pref_chroma;
    heif_error pref_err =
        heif_image_handle_get_preferred_decoding_colorspace(
            primary, &pref_cs, &pref_chroma);
    (void)pref_err;

    transform_image(primary, params, 8);
    heif_image_handle_release(primary);
  }

  /* Transform all top-level images */
  int nimages = heif_context_get_number_of_top_level_images(ctx);
  if (nimages > 0 && nimages < 50) {
    heif_item_id* ids = static_cast<heif_item_id*>(
        malloc(static_cast<size_t>(nimages) * sizeof(heif_item_id)));
    if (ids) {
      int got = heif_context_get_list_of_top_level_image_IDs(ctx, ids, nimages);
      for (int i = 0; i < got && i < 5; i++) {
        heif_image_handle* handle = nullptr;
        err = heif_context_get_image_handle(ctx, ids[i], &handle);
        if (err.code == heif_error_Ok && handle) {
          transform_image(handle, params, 8);
          heif_image_handle_release(handle);
        }
      }
      free(ids);
    }
  }

  heif_context_free(ctx);
  return 0;
}
