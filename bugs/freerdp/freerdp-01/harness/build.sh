#!/bin/bash
set -euo pipefail
cmd="${1:?usage: build.sh build-libs | harness <config>}"

# (TestFuzzNTLMMessage.c) includes "../sspi.h" — so it must live in
# winpr/libwinpr/sspi/test/. The Dockerfile copies it into the right
# place at image build time. Here we just configure + build winpr.

if [ "${cmd}" = "build-libs" ]; then
    JOBS=$(nproc)
    unset MAKEFLAGS MFLAGS

    for CONFIG_LIB in asan cov; do
        case "${CONFIG_LIB}" in
            asan) CF="-fsanitize=address -g -O1"; LF="-fsanitize=address" ;;
            cov)  CF="-fprofile-instr-generate -fcoverage-mapping -g -O0"; LF="-fprofile-instr-generate -fcoverage-mapping" ;;
        esac

        cp -r /src/freerdp /src/freerdp-${CONFIG_LIB}
        BUILD_DIR=/src/freerdp-${CONFIG_LIB}/build
        mkdir -p "${BUILD_DIR}"
        pushd "${BUILD_DIR}" >/dev/null
        env CC=clang CXX=clang++ CFLAGS="${CF}" CXXFLAGS="${CF}" LDFLAGS="${LF}" \
            cmake .. \
                -DCMAKE_BUILD_TYPE=Debug \
                -DCMAKE_C_COMPILER=clang -DCMAKE_CXX_COMPILER=clang++ \
                -DCMAKE_C_FLAGS="${CF}" -DCMAKE_CXX_FLAGS="${CF}" \
                -DCMAKE_EXE_LINKER_FLAGS="${LF}" -DCMAKE_SHARED_LINKER_FLAGS="${LF}" \
                -DWITH_SAMPLE=OFF -DWITH_CLIENT=OFF -DWITH_SERVER=OFF \
                -DWITH_X11=OFF -DWITH_WAYLAND=OFF \
                -DBUILD_TESTING=OFF -DBUILD_SHARED_LIBS=OFF \
                -DBUILTIN_CHANNELS=OFF -DWITH_CHANNELS=OFF \
                -DWITH_KRB5=OFF -DWITH_AAD=OFF \
                -DWITH_FFMPEG=OFF -DWITH_DSP_FFMPEG=OFF -DWITH_SWSCALE=OFF \
                -DWITH_ALSA=OFF -DWITH_PULSE=OFF -DWITH_OSS=OFF \
                -DWITH_PCSC=OFF -DWITH_PKCS11=OFF \
                -DWITH_GSTREAMER_1_0=OFF -DWITH_GSM=OFF \
                -DWITH_CUPS=OFF -DWITH_DBUS=OFF -DWITH_LIBSYSTEMD=OFF \
                -DWITH_FUSE=OFF -DWITH_VIDEO_FFMPEG=OFF \
                -DWITH_FAAD2=OFF -DWITH_FAAC=OFF \
                -DWITH_WEBVIEW=OFF \
                -DUSE_UNWIND=OFF
        # Only build winpr — we don't need the rest
        make -j${JOBS} winpr || true
        popd >/dev/null
    done
    echo "freerdp winpr built"
    exit 0
fi

if [ "${cmd}" = "harness" ]; then
    CONFIG="${2:?harness needs <config>}"
    OUT=/out/${CONFIG}
    mkdir -p "${OUT}"
    case "${CONFIG}" in
        debug)        CFH="-g -O0"; BUILD=/src/freerdp-asan; SAN="-fsanitize=fuzzer,address" ;;
        debug-asan)   CFH="-g -O0"; BUILD=/src/freerdp-asan; SAN="-fsanitize=fuzzer,address" ;;
        release-asan) CFH="-O2 -g"; BUILD=/src/freerdp-asan; SAN="-fsanitize=fuzzer,address" ;;
        coverage)     CFH="-g -O0 -fprofile-instr-generate -fcoverage-mapping"; BUILD=/src/freerdp-cov; SAN="-fsanitize=fuzzer" ;;
        *) echo "unknown config: ${CONFIG}" >&2; exit 2 ;;
    esac

    # Harness lives inside winpr/libwinpr/sspi/test/ so its "../sspi.h" resolves.
    HARNESS_DIR=${BUILD}/winpr/libwinpr/sspi/test
    cp /src/harness/TestFuzzNTLMMessage.c "${HARNESS_DIR}/"

    # rpath '$ORIGIN/../lib' lets the binary find bundled ICU .so files
    # next to the binaries/ tree without LD_LIBRARY_PATH (binaries/lib/).
    clang ${CFH} ${SAN} -fmacro-prefix-map=/src/= \
        -I "${BUILD}/winpr/include" \
        -I "${BUILD}/build/winpr/include" \
        -I "${BUILD}/include" \
        "${HARNESS_DIR}/TestFuzzNTLMMessage.c" \
        "${BUILD}/build/winpr/libwinpr/libwinpr3.a" \
        -Wl,-rpath,'$ORIGIN/../lib' \
        -lssl -lcrypto -licuuc -licui18n -licudata -lpthread -lm -ldl \
        -o "${OUT}/harness"

    echo "built ${OUT}/harness ($(stat -c %s "${OUT}/harness") bytes)"
    exit 0
fi
exit 2
