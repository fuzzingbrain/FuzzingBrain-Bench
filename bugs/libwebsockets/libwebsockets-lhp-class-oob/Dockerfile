# syntax=docker/dockerfile:1.6
FROM debian:bookworm-slim

ARG VULN_COMMIT=8a422a736b84191a2fd4ec492d82888096329817
ARG SOURCE_DATE_EPOCH=1735689600
ENV SOURCE_DATE_EPOCH=${SOURCE_DATE_EPOCH}
ENV DEBIAN_FRONTEND=noninteractive

RUN apt-get update && apt-get install -y --no-install-recommends \
        git ca-certificates \
        clang libclang-rt-14-dev \
        cmake make build-essential pkg-config \
        libcap-dev \
    && rm -rf /var/lib/apt/lists/*

RUN git clone --filter=blob:none https://github.com/warmcat/libwebsockets /src/libwebsockets \
 && git -C /src/libwebsockets checkout ${VULN_COMMIT}

COPY harness/lws_lhp_fuzzer.cc /src/harness/lws_lhp_fuzzer.cc
COPY harness/build.sh          /src/harness/build.sh
RUN chmod +x /src/harness/build.sh

RUN /src/harness/build.sh build-libs

RUN mkdir -p /out \
 && /src/harness/build.sh harness debug \
 && /src/harness/build.sh harness debug-asan \
 && /src/harness/build.sh harness release-asan \
 && /src/harness/build.sh harness coverage

RUN ls -la /out/*/harness
