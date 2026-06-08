#!/bin/bash
set -euo pipefail
cmd="${1:?usage: build.sh build-libs | harness <config>}"

# =============================================================================
# WARNING / KNOWN GAP (see ../NOTES.md):
#   Skia is a very large build. A free-standing `clang++ ... -lskia` link is
#   unworkable: libskia.a transitively depends on dozens of in-tree libraries
#   (skcms, harfbuzz, freetype, ICU, libc++, abseil, etc.) that are not exposed
#   as a single archive. The faithful build path is Skia's own GN/Ninja graph,
#   which still requires the full Skia checkout + bundled clang + a third_party
#   sync (multi-GB, long build). This script encodes that path but was NOT
#   executed/validated in this benchmark copy (NO docker / NO compile per task
#   brief). The benchmark Dockerfile may be infeasible to build in a standard
#   CI box for this reason.
# =============================================================================

SRC=/src/skia

if [ "${cmd}" = "build-libs" ]; then
    JOBS=$(nproc)
    unset MAKEFLAGS MFLAGS

    cd "${SRC}"
    # Skia bundles its toolchain + most third_party deps via this script.
    python3 tools/git-sync-deps

    # Fetch Skia's pinned clang + GN/Ninja.
    bin/fetch-gn
    bin/fetch-ninja || true

    for CONFIG_LIB in asan cov; do
        OUTGN="${SRC}/out/${CONFIG_LIB}"
        case "${CONFIG_LIB}" in
            asan)
                ARGS='is_debug=false
                      is_official_build=false
                      skia_use_fontconfig=false
                      skia_enable_skshaper=false
                      skia_use_system_libpng=false
                      skia_use_system_libjpeg_turbo=false
                      skia_use_system_zlib=false
                      sanitize="ASAN"
                      extra_cflags=["-fsanitize=fuzzer-no-link","-DSK_ENABLE_DUMP_GPU=0"]' ;;
            cov)
                ARGS='is_debug=false
                      is_official_build=false
                      skia_enable_skshaper=false
                      extra_cflags=["-fprofile-instr-generate","-fcoverage-mapping"]
                      extra_ldflags=["-fprofile-instr-generate","-fcoverage-mapping"]' ;;
        esac
        bin/gn gen "${OUTGN}" --args="${ARGS}"
        # Build only the static Skia archive; the harness is linked separately.
        ninja -C "${OUTGN}" -j"${JOBS}" skia
    done
    echo "skia libs built"
    exit 0
fi

if [ "${cmd}" = "harness" ]; then
    CONFIG="${2:?harness needs <config>}"
    OUT=/out/${CONFIG}
    mkdir -p "${OUT}"
    case "${CONFIG}" in
        debug)        CFH="-g -O0"; LIBGN=/src/skia/out/asan; SAN="-fsanitize=fuzzer,address" ;;
        debug-asan)   CFH="-g -O0"; LIBGN=/src/skia/out/asan; SAN="-fsanitize=fuzzer,address" ;;
        release-asan) CFH="-O2 -g"; LIBGN=/src/skia/out/asan; SAN="-fsanitize=fuzzer,address" ;;
        coverage)     CFH="-g -O0 -fprofile-instr-generate -fcoverage-mapping"; LIBGN=/src/skia/out/cov; SAN="-fsanitize=fuzzer" ;;
        *) echo "unknown config: ${CONFIG}" >&2; exit 2 ;;
    esac

    # Link the libFuzzer harness against the Skia static archive built above.
    # NOTE: depending on the gn config, libskia.a may still require additional
    # bundled third_party archives under ${LIBGN}/obj/third_party/. This link
    # line was NOT validated (see NOTES.md); it documents the intended shape.
    clang++ -std=c++17 ${CFH} ${SAN} -fmacro-prefix-map=/src/= \
        -I "${SRC}" \
        /src/harness/skia_image_filter_chain_construction_fuzzer.cc \
        "${LIBGN}/libskia.a" \
        -lpthread -lm -ldl \
        -o "${OUT}/harness"

    echo "built ${OUT}/harness ($(stat -c %s "${OUT}/harness") bytes)"
    exit 0
fi
exit 2
