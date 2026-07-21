# syntax=docker/dockerfile:1.6
# --platform=linux/amd64 is required: FBB grading runs on linux/amd64.
# Without it, Apple Silicon builds aarch64 binaries that won't execute on
# the grading host.
FROM --platform=linux/amd64 debian:bookworm-slim
ARG VULN_COMMIT=6a10c829fb645e0de1408030e6e0f67e820b0c98
ARG FIX_COMMIT=84fbcef8a558b1da075417a89d29aa5632d57f63
ARG SOURCE_DATE_EPOCH=1735689600
ENV SOURCE_DATE_EPOCH=${SOURCE_DATE_EPOCH}
ENV FIX_COMMIT=${FIX_COMMIT}
ENV DEBIAN_FRONTEND=noninteractive

RUN apt-get update && apt-get install -y --no-install-recommends \
        git ca-certificates clang libclang-rt-14-dev \
        build-essential autoconf automake libtool pkg-config \
        libxml2-dev \
    && rm -rf /var/lib/apt/lists/*

RUN git clone --depth 1 https://github.com/ImageMagick/ImageMagick /src/ImageMagick \
 && git -C /src/ImageMagick fetch --depth 1 origin ${VULN_COMMIT} \
 && git -C /src/ImageMagick checkout ${VULN_COMMIT}

COPY harness/dcm_fuzzer.cc /src/harness/dcm_fuzzer.cc
COPY harness/build.sh      /src/harness/build.sh
RUN chmod +x /src/harness/build.sh

RUN /src/harness/build.sh build-libs
RUN FIX_COMMIT=${FIX_COMMIT} /src/harness/build.sh build-fixed-libs
RUN mkdir -p /out \
 && /src/harness/build.sh harness debug \
 && /src/harness/build.sh harness debug-asan \
 && /src/harness/build.sh harness release-asan \
 && /src/harness/build.sh harness fixed-asan \
 && /src/harness/build.sh harness coverage

RUN ls -la /out/*/harness
