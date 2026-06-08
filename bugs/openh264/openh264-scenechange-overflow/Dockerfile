# syntax=docker/dockerfile:1.6
FROM debian:bookworm-slim

ARG VULN_COMMIT=cf568c83f71a18778f9a16e344effaf40c11b752
ARG SOURCE_DATE_EPOCH=1735689600
ENV SOURCE_DATE_EPOCH=${SOURCE_DATE_EPOCH}
ENV DEBIAN_FRONTEND=noninteractive

RUN apt-get update && apt-get install -y --no-install-recommends \
        git ca-certificates \
        clang libclang-rt-14-dev \
        make build-essential pkg-config \
    && rm -rf /var/lib/apt/lists/*

RUN git clone --filter=blob:none https://github.com/cisco/openh264 /src/openh264 \
 && git -C /src/openh264 checkout ${VULN_COMMIT}

COPY harness/processing_fuzzer.cpp /src/harness/processing_fuzzer.cpp
COPY harness/build.sh              /src/harness/build.sh
RUN chmod +x /src/harness/build.sh

RUN /src/harness/build.sh build-libs

RUN mkdir -p /out \
 && /src/harness/build.sh harness debug \
 && /src/harness/build.sh harness debug-asan \
 && /src/harness/build.sh harness release-asan \
 && /src/harness/build.sh harness coverage

RUN ls -la /out/*/harness
