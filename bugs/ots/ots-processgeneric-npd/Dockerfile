# syntax=docker/dockerfile:1.6
FROM debian:bookworm-slim

ARG VULN_COMMIT=8510bfd8c95350fc022552940a45120ff6e737b5
ARG SOURCE_DATE_EPOCH=1735689600
ENV SOURCE_DATE_EPOCH=${SOURCE_DATE_EPOCH}
ENV DEBIAN_FRONTEND=noninteractive

RUN apt-get update && apt-get install -y --no-install-recommends \
        git ca-certificates \
        clang libclang-rt-14-dev \
        build-essential meson ninja-build pkg-config \
        zlib1g-dev libbrotli-dev libfreetype-dev \
        liblz4-dev libwoff-dev \
    && rm -rf /var/lib/apt/lists/*

RUN git clone --recurse-submodules https://github.com/khaledhosny/ots /src/ots \
 && git -C /src/ots checkout ${VULN_COMMIT} \
 && git -C /src/ots submodule update --init --recursive

COPY harness/fuzz_ots_passthru.cc /src/harness/fuzz_ots_passthru.cc
COPY harness/passthru_harness.cc  /src/harness/passthru_harness.cc
COPY harness/build.sh             /src/harness/build.sh
RUN chmod +x /src/harness/build.sh

RUN /src/harness/build.sh build-libs

RUN mkdir -p /out \
 && /src/harness/build.sh harness debug \
 && /src/harness/build.sh harness debug-asan \
 && /src/harness/build.sh harness release-asan \
 && /src/harness/build.sh harness coverage

RUN ls -la /out/*/harness
