# syntax=docker/dockerfile:1.6
FROM debian:bookworm-slim
ARG VULN_COMMIT=6f31db9b07829dcd7f166da85405eecdf889a1c8
ARG SOURCE_DATE_EPOCH=1735689600
ENV SOURCE_DATE_EPOCH=${SOURCE_DATE_EPOCH}
ENV DEBIAN_FRONTEND=noninteractive

# Toolchain (clang + libFuzzer runtime), Meson/Ninja, and the systemd build
# dependencies that are hard-required even for a minimal fuzz build.
RUN apt-get update && apt-get install -y --no-install-recommends \
        git ca-certificates pkg-config \
        clang libclang-rt-14-dev lld \
        meson ninja-build python3 python3-jinja2 \
        gperf patchelf libcap-dev libmount-dev libblkid-dev libkmod-dev \
        libssl-dev \
    && rm -rf /var/lib/apt/lists/*

RUN git clone https://github.com/systemd/systemd /src/systemd \
 && git -C /src/systemd checkout ${VULN_COMMIT}

COPY harness/fuzz-hwdb.c /src/harness/fuzz-hwdb.c
COPY harness/build.sh    /src/harness/build.sh
RUN chmod +x /src/harness/build.sh

RUN /src/harness/build.sh build-libs

RUN mkdir -p /out \
 && /src/harness/build.sh harness debug \
 && /src/harness/build.sh harness debug-asan \
 && /src/harness/build.sh harness release-asan \
 && /src/harness/build.sh harness coverage

RUN ls -la /out/*/harness
