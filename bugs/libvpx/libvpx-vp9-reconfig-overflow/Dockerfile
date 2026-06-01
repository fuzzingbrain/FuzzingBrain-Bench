# syntax=docker/dockerfile:1.6
FROM debian:bookworm-slim
ARG VULN_COMMIT=a5e2e6528374c8ae7cfe8ef6b7aad4fc327c8688
ARG SOURCE_DATE_EPOCH=1735689600
ENV SOURCE_DATE_EPOCH=${SOURCE_DATE_EPOCH}
ENV DEBIAN_FRONTEND=noninteractive

RUN apt-get update && apt-get install -y --no-install-recommends \
        git ca-certificates clang libclang-rt-14-dev \
        make build-essential pkg-config nasm yasm perl \
    && rm -rf /var/lib/apt/lists/*

RUN git clone https://github.com/webmproject/libvpx /src/libvpx \
 && git -C /src/libvpx checkout ${VULN_COMMIT}

COPY harness/vp9_encoder_midstream_reconfig_fuzzer.cc /src/harness/vp9_encoder_midstream_reconfig_fuzzer.cc
COPY harness/build.sh                                 /src/harness/build.sh
RUN chmod +x /src/harness/build.sh

RUN /src/harness/build.sh build-libs

RUN mkdir -p /out \
 && /src/harness/build.sh harness debug \
 && /src/harness/build.sh harness debug-asan \
 && /src/harness/build.sh harness release-asan \
 && /src/harness/build.sh harness coverage

RUN ls -la /out/*/harness
