/*
 * Copyright (c) 2026, Alliance for Open Media. All rights reserved.
 *
 * This source code is subject to the terms of the BSD 2 Clause License.
 */

/*
 * Fuzz target: read_av1config / get_av1config_from_obu
 * ----------------------------------------------------
 *
 * Exercises common/av1_config.c — parsers for the ISOBMFF/Matroska
 * AV1CodecConfigurationBox (`av1C`).  The same bytes are parsed by
 * Chromium, Firefox, Android MediaExtractor, GStreamer, and ffmpeg
 * when handling AV1 in MP4/WebM containers, so bugs here have wide
 * blast radius and are directly attacker-influenceable over the web.
 *
 * Input format:
 *   byte[0]        : low bit chooses is_annexb for get_av1config_from_obu
 *   byte[1..]      : raw bytes handed to both parser entry points.
 */

#include <stddef.h>
#include <stdint.h>
#include <string.h>

#include "common/av1_config.h"

extern "C" int LLVMFuzzerTestOneInput(const uint8_t *data, size_t size) {
  if (size == 0) return 0;

  // Part 1: read_av1config — parses the raw `av1C` box body.
  {
    Av1Config cfg;
    memset(&cfg, 0, sizeof(cfg));
    size_t bytes_read = 0;
    read_av1config(data, size, &bytes_read, &cfg);
  }

  // Part 2: get_av1config_from_obu — parses a Sequence Header OBU from
  // a (possibly annex-B) buffer.  Consume the first byte as a mode
  // selector so the fuzzer can drive both paths.
  {
    const int is_annexb = data[0] & 1;
    Av1Config cfg;
    memset(&cfg, 0, sizeof(cfg));
    get_av1config_from_obu(data + 1, size - 1, is_annexb, &cfg);
  }

  return 0;
}
