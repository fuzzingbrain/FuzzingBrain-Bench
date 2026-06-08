# syntax=docker/dockerfile:1.6
FROM debian:bookworm-slim
# Pinned commit from the bug report (affected main branch, 2026-04-13).
ARG VULN_COMMIT=e223d69b36574c4a2b10dbd27761753de81624ab
ARG SOURCE_DATE_EPOCH=1735689600
ENV SOURCE_DATE_EPOCH=${SOURCE_DATE_EPOCH}
ENV DEBIAN_FRONTEND=noninteractive

RUN apt-get update && apt-get install -y --no-install-recommends \
        git ca-certificates clang libclang-rt-14-dev \
        cmake make build-essential pkg-config \
    && rm -rf /var/lib/apt/lists/*

RUN git clone https://github.com/google/flatbuffers /src/flatbuffers \
 && git -C /src/flatbuffers checkout ${VULN_COMMIT}

COPY harness/flatbuffers_reflection_gentext_fuzzer.cc /src/harness/flatbuffers_reflection_gentext_fuzzer.cc
COPY harness/build.sh                                  /src/harness/build.sh
RUN chmod +x /src/harness/build.sh

RUN /src/harness/build.sh build-libs

RUN mkdir -p /out \
 && /src/harness/build.sh harness debug \
 && /src/harness/build.sh harness debug-asan \
 && /src/harness/build.sh harness release-asan \
 && /src/harness/build.sh harness coverage

RUN ls -la /out/*/harness /out/*/monster_test.bfbs
