# syntax=docker/dockerfile:1.6
FROM debian:bookworm-slim

ARG VULN_COMMIT=62f1b8c76ed4d8305071fdacbe74ef9717bacac5
ARG DE265_TAG=v1.0.15
ARG SOURCE_DATE_EPOCH=1735689600
ENV SOURCE_DATE_EPOCH=${SOURCE_DATE_EPOCH}
ENV DEBIAN_FRONTEND=noninteractive

RUN apt-get update && apt-get install -y --no-install-recommends \
        git ca-certificates \
        clang libclang-rt-14-dev \
        cmake make build-essential pkg-config \
    && rm -rf /var/lib/apt/lists/*

RUN git clone --filter=blob:none https://github.com/strukturag/libde265 /src/libde265 \
 && git -C /src/libde265 checkout ${DE265_TAG}

RUN git clone --filter=blob:none https://github.com/strukturag/libheif /src/libheif \
 && git -C /src/libheif checkout ${VULN_COMMIT}

COPY harness/image_transform_fuzzer.cc /src/harness/image_transform_fuzzer.cc
COPY harness/build.sh                  /src/harness/build.sh
RUN chmod +x /src/harness/build.sh

RUN /src/harness/build.sh build-libs

RUN mkdir -p /out \
 && /src/harness/build.sh harness debug \
 && /src/harness/build.sh harness debug-asan \
 && /src/harness/build.sh harness release-asan \
 && /src/harness/build.sh harness coverage

RUN ls -la /out/*/harness
