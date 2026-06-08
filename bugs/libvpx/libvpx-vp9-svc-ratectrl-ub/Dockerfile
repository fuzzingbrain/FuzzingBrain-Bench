# syntax=docker/dockerfile:1.6
FROM debian:bookworm-slim
ARG VULN_COMMIT=3c456eb6eea2fcea46115d61eb72014d4f882541
ARG SOURCE_DATE_EPOCH=1735689600
ENV SOURCE_DATE_EPOCH=${SOURCE_DATE_EPOCH}
ENV DEBIAN_FRONTEND=noninteractive

RUN apt-get update && apt-get install -y --no-install-recommends \
        git ca-certificates clang libclang-rt-14-dev \
        make build-essential pkg-config nasm yasm perl python3 \
    && rm -rf /var/lib/apt/lists/*

RUN git clone https://chromium.googlesource.com/webm/libvpx /src/libvpx \
 && git -C /src/libvpx checkout ${VULN_COMMIT}

COPY harness/vp9_encoder_svc_layer_config_fuzzer.cc /src/harness/vp9_encoder_svc_layer_config_fuzzer.cc
COPY harness/build.sh                               /src/harness/build.sh
RUN chmod +x /src/harness/build.sh

RUN /src/harness/build.sh build-libs

RUN mkdir -p /out \
 && /src/harness/build.sh harness debug \
 && /src/harness/build.sh harness debug-asan \
 && /src/harness/build.sh harness release-asan \
 && /src/harness/build.sh harness coverage

RUN ls -la /out/*/harness
