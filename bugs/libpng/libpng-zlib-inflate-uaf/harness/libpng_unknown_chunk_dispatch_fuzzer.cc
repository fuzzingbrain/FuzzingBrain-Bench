/* libpng_unknown_chunk_dispatch_fuzzer.cc
 *
 * Copyright (c) 2018-2026 Cosmin Truta
 * Copyright (c) 1998-2002,2004,2006-2018 Glenn Randers-Pehrson
 * Copyright (c) 1996-1997 Andreas Dilger
 * Copyright (c) 1995-1996 Guy Eric Schalnat, Group 42, Inc.
 *
 * This code is released under the libpng license.
 * For conditions of distribution and use, see the disclaimer
 * and license in png.h
 */

// libFuzzer harness for Logic Group: libpng_unknown_chunk_dispatch
//
// Exercises the unknown-chunk keep/skip dispatch matrix that no existing
// libpng fuzzer touches. Specifically:
//
//   * png_set_keep_unknown_chunks with attacker-selected policy
//     (DEFAULT / NEVER / IF_SAFE / ALWAYS) and an attacker-selected
//     chunk-name list (NULL, single entry, or full list);
//   * png_set_read_user_chunk_fn installing a callback whose return
//     value (-1 / 0 / 1) cross-multiplies with the keep policy;
//   * the downstream png_cache_unknown_chunk + png_store_unknown_chunk
//     path reached via png_read_info once IHDR is parsed.
//
// Paper context: existing contrib/oss-fuzz fuzzers all use the default
// "skip unknown" behavior, so png_cache_unknown_chunk / png_store_unknown
// chunk / png_handle_unknown branches never fire under fuzz. Historical
// CVE-2014-9495 / CVE-2015-0973 / CVE-2016-10087 cluster in exactly this
// region. Real-caller studied: contrib/libtests/pngunknown.c (upstream
// libpng's own unknown-chunk test), which was the template for init
// order and callback semantics below.

#include <stddef.h>
#include <stdint.h>
#include <stdlib.h>
#include <string.h>

#include <vector>

#include <fuzzer/FuzzedDataProvider.h>

#include "png.h"

namespace {

struct BufState {
  const uint8_t* data;
  size_t bytes_left;
};

struct HarnessState {
  png_structp png_ptr = nullptr;
  png_infop info_ptr = nullptr;
  png_infop end_info_ptr = nullptr;
  BufState* buf_state = nullptr;
  // Callback-return mode picked from the fuzz prefix. Kept on the state
  // struct (not a static global) so repeated invocations of
  // LLVMFuzzerTestOneInput cannot bleed state across calls.
  int user_chunk_return_mode = 0;
};

// Custom allocator capping single allocations. Keeps ASan-OOM noise out
// of the picture so genuine OOB / UAF in the cache/store path is visible.
void* limited_malloc(png_structp, png_alloc_size_t size) {
  if (size > 8 * 1024 * 1024) return nullptr;
  return malloc(size);
}
void limited_free(png_structp, png_voidp ptr) { free(ptr); }

// Custom byte-stream reader. Same shape used in
// contrib/oss-fuzz/libpng_read_fuzzer.cc — bytes come from an in-memory
// BufState rather than a FILE*.
void user_read_data(png_structp png_ptr, png_bytep dst, size_t length) {
  auto* bs = static_cast<BufState*>(png_get_io_ptr(png_ptr));
  if (!bs || length > bs->bytes_left) {
    png_error(png_ptr, "read error");
    return;
  }
  memcpy(dst, bs->data, length);
  bs->data += length;
  bs->bytes_left -= length;
}

// User chunk callback — libpng contract: return -1 = error, 0 = not
// handled (libpng applies its own keep/skip rules), 1 = handled (libpng
// discards the chunk). We use this exact semantics from the upstream
// pngunknown.c:read_callback template. Mode is pulled from the fuzz
// prefix via HarnessState so the fuzzer explores all three return
// regimes.
int user_chunk_cb(png_structp png_ptr, png_unknown_chunkp chunk) {
  auto* st = static_cast<HarnessState*>(png_get_user_chunk_ptr(png_ptr));
  if (!st || !chunk) return 0;

  switch (st->user_chunk_return_mode) {
    case 0:
      // Not handled: libpng's own keep list decides.
      return 0;
    case 1:
      // Handled: discard.
      return 1;
    case 2:
      // Error path: libpng treats this as a fatal error and longjmps.
      // We still arm jmpbuf before png_read_info, so this is safe.
      return -1;
    default:
      return 0;
  }
}

void cleanup(HarnessState& st) {
  if (st.png_ptr) {
    if (st.end_info_ptr) {
      png_destroy_read_struct(&st.png_ptr, &st.info_ptr, &st.end_info_ptr);
    } else if (st.info_ptr) {
      png_destroy_read_struct(&st.png_ptr, &st.info_ptr, nullptr);
    } else {
      png_destroy_read_struct(&st.png_ptr, nullptr, nullptr);
    }
    st.png_ptr = nullptr;
    st.info_ptr = nullptr;
    st.end_info_ptr = nullptr;
  }
  if (st.buf_state) {
    delete st.buf_state;
    st.buf_state = nullptr;
  }
}

// Valid 4-byte PNG chunk-name candidates. Each MUST be a well-formed PNG
// chunk name (ASCII letter per byte) to pass libpng's own name validator
// in png_set_keep_unknown_chunks. The case-bit encodes "critical" (upper
// first letter) vs "ancillary" (lower first letter); our aim is to drive
// both code paths.
const png_byte kChunkCandidates[][5] = {
    {'v','p','A','g', 0},  // ancillary, private, unsafe-to-copy (common)
    {'c','H','R','M', 0},  // ancillary, public, safe-to-copy
    {'p','H','Y','s', 0},  // ancillary, public, safe-to-copy
    {'o','F','F','s', 0},  // ancillary, public, unsafe-to-copy
    {'s','C','A','L', 0},  // ancillary, public, unsafe-to-copy
    {'e','X','I','f', 0},  // ancillary, public, safe-to-copy
    {'s','T','E','R', 0},  // ancillary, public, unsafe-to-copy
    {'I','D','O','T', 0},  // critical, unsafe-to-copy (Apple private)
};
constexpr size_t kNumChunkCandidates =
    sizeof(kChunkCandidates) / sizeof(kChunkCandidates[0]);

}  // namespace

extern "C" int LLVMFuzzerTestOneInput(const uint8_t* data, size_t size) {
  // Need at least the 8-byte PNG signature + one chunk header (8 bytes)
  // + the few bytes of fuzz-controlled config prefix we consume below.
  if (size < 32) return 0;

  FuzzedDataProvider fdp(data, size);

  // Pull the configuration prefix from the fuzz bytes. All of these drive
  // the watched code paths directly:
  //   * keep_policy        → PNG_HANDLE_CHUNK_* selector for the global
  //                          default call (num_chunks=0 / chunks=NULL).
  //   * keep_list_mode     → 0 = no per-chunk override list,
  //                          1 = single chunk override,
  //                          2 = multi-chunk override list,
  //                          3 = override "all" with num_chunks=-1.
  //   * user_chunk_mode    → 0 = no callback, 1 = callback-returns-0,
  //                          2 = callback-returns-1, 3 = callback-errors.
  //   * num_override       → 1..kNumChunkCandidates for modes 1/2.
  //   * list_index_seed    → selects which entries go into the list.
  int keep_policy_idx = fdp.ConsumeIntegralInRange<int>(0, 3);
  int keep_list_mode  = fdp.ConsumeIntegralInRange<int>(0, 3);
  int user_chunk_mode = fdp.ConsumeIntegralInRange<int>(0, 3);
  int num_override    = fdp.ConsumeIntegralInRange<int>(
      1, static_cast<int>(kNumChunkCandidates));
  uint32_t list_index_seed = fdp.ConsumeIntegral<uint32_t>();
  // Also pick user limits — the cache path is cross-cut by
  // png_set_chunk_cache_max / png_set_chunk_malloc_max because
  // png_cache_unknown_chunk consults both before the copy.
  png_uint_32 chunk_cache_max =
      fdp.ConsumeIntegralInRange<png_uint_32>(0, 64);
  png_alloc_size_t chunk_malloc_max =
      fdp.ConsumeIntegralInRange<png_alloc_size_t>(0, 1 << 20);

  const int kKeepPolicies[4] = {
      PNG_HANDLE_CHUNK_AS_DEFAULT,
      PNG_HANDLE_CHUNK_NEVER,
      PNG_HANDLE_CHUNK_IF_SAFE,
      PNG_HANDLE_CHUNK_ALWAYS,
  };
  int keep_policy = kKeepPolicies[keep_policy_idx];

  // Remaining bytes = actual PNG stream.
  std::vector<uint8_t> payload = fdp.ConsumeRemainingBytes<uint8_t>();
  if (payload.size() < 8) return 0;
  // Require a valid PNG signature; otherwise libpng bails at byte 0 and
  // the unknown-chunk dispatch code is never reached — wasted invocation.
  if (png_sig_cmp(payload.data(), 0, 8) != 0) return 0;

  HarnessState st;
  st.user_chunk_return_mode =
      (user_chunk_mode == 0) ? 0 : user_chunk_mode - 1;

  st.png_ptr = png_create_read_struct(PNG_LIBPNG_VER_STRING, nullptr,
                                      nullptr, nullptr);
  if (!st.png_ptr) return 0;

  st.info_ptr = png_create_info_struct(st.png_ptr);
  if (!st.info_ptr) {
    cleanup(st);
    return 0;
  }

  st.end_info_ptr = png_create_info_struct(st.png_ptr);
  if (!st.end_info_ptr) {
    cleanup(st);
    return 0;
  }

  // P1: arm setjmp BEFORE any API that can longjmp. png_set_keep_unknown
  // _chunks validates chunk names and can png_error on an invalid entry;
  // png_set_read_user_chunk_fn itself does not longjmp but the callback
  // path during png_read_info can, and our callback returning -1 does
  // trigger libpng's internal png_error. All cleanup is via cleanup(st),
  // not via destructors, so the longjmp target below handles every
  // allocation.
  if (setjmp(png_jmpbuf(st.png_ptr))) {
    cleanup(st);
    return 0;
  }

  // Install the capped allocator and relax CRC so a single CRC bitflip
  // doesn't short-circuit the parser before it reaches unknown-chunk
  // handling. (Matches libpng_read_fuzzer.cc upstream conventions.)
  png_set_mem_fn(st.png_ptr, nullptr, limited_malloc, limited_free);
  png_set_crc_action(st.png_ptr, PNG_CRC_QUIET_USE, PNG_CRC_QUIET_USE);
#ifdef PNG_IGNORE_ADLER32
  png_set_option(st.png_ptr, PNG_IGNORE_ADLER32, PNG_OPTION_ON);
#endif

  // Arm user-limit caps. Per the LG notes, chunk_cache_max and
  // chunk_malloc_max are consulted by png_cache_unknown_chunk BEFORE the
  // memcpy, so setting them here is what pushes the fuzzer at the
  // boundary-arithmetic paths.
  png_set_user_limits(st.png_ptr, 16384, 16384);
  png_set_chunk_cache_max(st.png_ptr, chunk_cache_max);
  png_set_chunk_malloc_max(st.png_ptr, chunk_malloc_max);

  // STEP 1 — global default keep policy.
  // Per pngunknown.c:753 real-caller template, num_chunks=0 + NULL list
  // sets the library-wide default policy. This is safe regardless of
  // SAVE_UNKNOWN_CHUNKS support.
  png_set_keep_unknown_chunks(st.png_ptr, keep_policy, nullptr, 0);

  // STEP 2 — per-chunk overrides. Exercises the chunk-name validator
  // inside pngset.c and the keep-list memcpy that accepts caller-owned
  // name buffers.
  if (keep_list_mode == 1) {
    int idx = list_index_seed % kNumChunkCandidates;
    png_byte name[5];
    memcpy(name, kChunkCandidates[idx], 5);
    png_set_keep_unknown_chunks(st.png_ptr, keep_policy, name, 1);
  } else if (keep_list_mode == 2) {
    // Build a small list of chunk names from the seed.
    std::vector<png_byte> name_blob;
    name_blob.reserve(static_cast<size_t>(num_override) * 5);
    uint32_t seed = list_index_seed;
    for (int i = 0; i < num_override; ++i) {
      int idx = seed % kNumChunkCandidates;
      seed = seed * 1664525u + 1013904223u;
      for (int b = 0; b < 5; ++b) {
        name_blob.push_back(kChunkCandidates[idx][b]);
      }
    }
    png_set_keep_unknown_chunks(st.png_ptr, keep_policy,
                                name_blob.data(), num_override);
  } else if (keep_list_mode == 3) {
    // "all" override, num_chunks = -1. Real-caller template at
    // pngunknown.c:768.
    png_set_keep_unknown_chunks(st.png_ptr, keep_policy, nullptr, -1);
  }
  // keep_list_mode == 0 → leave global default from STEP 1.

  // STEP 3 — optionally install the user_chunk_fn.
  if (user_chunk_mode != 0) {
    png_set_read_user_chunk_fn(st.png_ptr, &st, user_chunk_cb);
  }

  // STEP 4 — feed bytes through png_read_info. This is what drives
  // png_read_chunk_header → png_handle_unknown → (user_chunk_cb?) →
  // png_cache_unknown_chunk → png_store_unknown_chunk.
  st.buf_state = new BufState{payload.data(), payload.size()};
  png_set_read_fn(st.png_ptr, st.buf_state, user_read_data);
  png_read_info(st.png_ptr, st.info_ptr);

  // STEP 5 — retrieve and inspect the stored unknown chunks. This forces
  // the png_get_unknown_chunks accessor path (a public API that the four
  // existing fuzzers never exercise).
#ifdef PNG_READ_UNKNOWN_CHUNKS_SUPPORTED
  png_unknown_chunkp entries = nullptr;
  int n_entries =
      png_get_unknown_chunks(st.png_ptr, st.info_ptr, &entries);
  (void)n_entries;
  (void)entries;
#endif

  // STEP 6 — read remaining chunks (IDAT + post-IDAT unknowns) so the
  // "after_IDAT" branch in png_handle_unknown is also exercised. We
  // don't care about pixel output; png_read_end walks the trailing
  // chunk stream including ancillary chunks in the post-IDAT position.
  png_read_end(st.png_ptr, st.end_info_ptr);

  cleanup(st);
  return 0;
}
