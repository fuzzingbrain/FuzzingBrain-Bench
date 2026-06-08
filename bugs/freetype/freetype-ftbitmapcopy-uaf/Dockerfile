# syntax=docker/dockerfile:1.6
FROM debian:bookworm-slim

ARG VULN_COMMIT=d41d4943410cb942e02e0a8866f39be02378ecf5
ARG SOURCE_DATE_EPOCH=1735689600
ENV SOURCE_DATE_EPOCH=${SOURCE_DATE_EPOCH}
ENV DEBIAN_FRONTEND=noninteractive

RUN apt-get update && apt-get install -y --no-install-recommends \
        git ca-certificates \
        clang libclang-rt-14-dev \
        cmake make build-essential pkg-config \
    && rm -rf /var/lib/apt/lists/*

# github.com/freetype/freetype is the read-only mirror of the canonical
# gitlab.freedesktop.org/freetype/freetype; commit hashes are identical.
RUN git clone --filter=blob:none https://github.com/freetype/freetype /src/freetype \
 && git -C /src/freetype checkout ${VULN_COMMIT}

COPY harness/ftfuzzer_glyph.c /src/harness/ftfuzzer_glyph.c
COPY harness/build.sh         /src/harness/build.sh
RUN chmod +x /src/harness/build.sh

RUN /src/harness/build.sh build-libs

RUN mkdir -p /out \
 && /src/harness/build.sh harness debug \
 && /src/harness/build.sh harness debug-asan \
 && /src/harness/build.sh harness release-asan \
 && /src/harness/build.sh harness coverage

RUN ls -la /out/*/harness
