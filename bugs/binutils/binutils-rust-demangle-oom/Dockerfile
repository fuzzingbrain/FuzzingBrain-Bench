# syntax=docker/dockerfile:1.6
FROM debian:bookworm-slim
ARG VULN_COMMIT=96c87c6dd55c38519ad168230d0893797b62fd52
ARG SOURCE_DATE_EPOCH=1735689600
ENV SOURCE_DATE_EPOCH=${SOURCE_DATE_EPOCH}
ENV DEBIAN_FRONTEND=noninteractive

RUN apt-get update && apt-get install -y --no-install-recommends \
        git ca-certificates clang libclang-rt-14-dev \
        build-essential \
    && rm -rf /var/lib/apt/lists/*

# binutils-gdb is large; we only need libiberty/ + include/. The
# sourceware CDN 502s on partial-clone (tree:0) but accepts a plain
# shallow clone of master. We then fetch the specific vuln commit to a
# depth that includes it.
ENV GIT_TERMINAL_PROMPT=0
RUN git -c protocol.version=2 clone --no-tags \
        https://sourceware.org/git/binutils-gdb.git /src/binutils-gdb \
 && git -C /src/binutils-gdb checkout ${VULN_COMMIT}

COPY harness/fuzz_rust_demangle.c /src/harness/fuzz_rust_demangle.c
COPY harness/build.sh             /src/harness/build.sh
RUN chmod +x /src/harness/build.sh

RUN mkdir -p /out \
 && /src/harness/build.sh harness debug \
 && /src/harness/build.sh harness debug-asan \
 && /src/harness/build.sh harness release-asan \
 && /src/harness/build.sh harness coverage

RUN ls -la /out/*/harness
