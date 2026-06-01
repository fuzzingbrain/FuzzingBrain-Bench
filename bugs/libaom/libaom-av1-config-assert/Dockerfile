# syntax=docker/dockerfile:1.6
FROM debian:bookworm-slim
ARG VULN_COMMIT=f23c9437a
ARG SOURCE_DATE_EPOCH=1735689600
ENV SOURCE_DATE_EPOCH=${SOURCE_DATE_EPOCH}
ENV DEBIAN_FRONTEND=noninteractive

RUN apt-get update && apt-get install -y --no-install-recommends \
        git ca-certificates clang libclang-rt-14-dev \
        cmake make build-essential pkg-config nasm perl python3 \
    && rm -rf /var/lib/apt/lists/*

RUN git clone https://aomedia.googlesource.com/aom /src/aom \
 && git -C /src/aom checkout ${VULN_COMMIT}

COPY harness/av1_config_fuzzer.cc /src/harness/av1_config_fuzzer.cc
COPY harness/build.sh             /src/harness/build.sh
RUN chmod +x /src/harness/build.sh

RUN /src/harness/build.sh build-libs

RUN mkdir -p /out \
 && /src/harness/build.sh harness debug \
 && /src/harness/build.sh harness debug-asan \
 && /src/harness/build.sh harness release-asan \
 && /src/harness/build.sh harness coverage

RUN ls -la /out/*/harness
