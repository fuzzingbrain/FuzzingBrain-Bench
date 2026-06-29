#!/bin/bash
set -euo pipefail
cmd="${1:?usage: build.sh build-libs | build-fixed-libs | harness <config>}"

IM_CONFIGURE=(./configure --disable-shared --enable-static \
    --disable-docs --without-perl \
    --without-x --without-modules \
    --disable-openmp \
    --without-jpeg --without-png --without-tiff --without-webp \
    --without-zlib --without-bzlib --without-zstd --without-lzma \
    --without-freetype --without-fontconfig --without-pango \
    --without-raqm --without-djvu --without-jbig --without-jp2 --without-openjp2 \
    --without-fpx --without-flif --without-heic --without-jxl \
    --without-raw --without-lqr)

build_tree() {
    local tree="$1" cflags="$2" ldflags="$3"
    pushd "${tree}" >/dev/null
    env CC=clang CXX=clang++ CFLAGS="${cflags}" CXXFLAGS="${cflags}" LDFLAGS="${ldflags}" \
        "${IM_CONFIGURE[@]}"
    make -j"$(nproc)"
    popd >/dev/null
}

if [ "${cmd}" = "build-libs" ]; then
    JOBS=$(nproc)
    unset MAKEFLAGS MFLAGS

    for CONFIG_LIB in asan cov; do
        case "${CONFIG_LIB}" in
            asan) CF="-g -O1"; LF="" ;;
            cov)  CF="-fprofile-instr-generate -fcoverage-mapping -g -O0"; LF="-fprofile-instr-generate -fcoverage-mapping" ;;
        esac

        cp -r /src/ImageMagick "/src/im-${CONFIG_LIB}"
        build_tree "/src/im-${CONFIG_LIB}" "${CF}" "${LF}"
    done
    echo "ImageMagick vuln libs built"
    exit 0
fi

if [ "${cmd}" = "build-fixed-libs" ]; then
    FIX_COMMIT="${FIX_COMMIT:?FIX_COMMIT required}"
    cp -r /src/ImageMagick /src/im-fixed-asan
    git -C /src/im-fixed-asan fetch --depth 1 origin "${FIX_COMMIT}"
    git -C /src/im-fixed-asan checkout "${FIX_COMMIT}"
    build_tree "/src/im-fixed-asan" "-g -O1" ""
    echo "ImageMagick fixed libs built at ${FIX_COMMIT}"
    exit 0
fi

if [ "${cmd}" = "harness" ]; then
    CONFIG="${2:?harness needs <config>}"
    OUT=/out/${CONFIG}
    mkdir -p "${OUT}"
    case "${CONFIG}" in
        debug)        CFH="-g -O0"; BUILD=/src/im-asan; SAN="-fsanitize=fuzzer" ;;
        debug-asan)   CFH="-g -O0"; BUILD=/src/im-asan; SAN="-fsanitize=fuzzer" ;;
        release-asan) CFH="-O2 -g"; BUILD=/src/im-asan; SAN="-fsanitize=fuzzer" ;;
        fixed-asan)   CFH="-O2 -g"; BUILD=/src/im-fixed-asan; SAN="-fsanitize=fuzzer" ;;
        coverage)     CFH="-g -O0 -fprofile-instr-generate -fcoverage-mapping"; BUILD=/src/im-cov; SAN="-fsanitize=fuzzer" ;;
        *) echo "unknown config: ${CONFIG}" >&2; exit 2 ;;
    esac

    clang++ ${CFH} ${SAN} -fmacro-prefix-map=/src/= -std=c++17 \
        -DMAGICKCORE_QUANTUM_DEPTH=16 -DMAGICKCORE_HDRI_ENABLE=1 \
        -I "${BUILD}" -I "${BUILD}/MagickCore" \
        /src/harness/dcm_fuzzer.cc \
        "${BUILD}/MagickCore/.libs/libMagickCore-7.Q16HDRI.a" \
        -lxml2 -lpthread -lm \
        -o "${OUT}/harness"

    echo "built ${OUT}/harness ($(stat -c %s "${OUT}/harness") bytes)"
    exit 0
fi
exit 2
