# syntax=docker/dockerfile:1.6
FROM debian:bookworm-slim
ARG VULN_COMMIT=1eefab41bc0ab1c6c2c1fd3e4a49e3ee1849751d
ARG SOURCE_DATE_EPOCH=1735689600
ENV SOURCE_DATE_EPOCH=${SOURCE_DATE_EPOCH}
ENV DEBIAN_FRONTEND=noninteractive

RUN apt-get update && apt-get install -y --no-install-recommends \
        git ca-certificates clang libclang-rt-14-dev \
        build-essential autoconf automake libtool pkg-config \
        libxml2-dev \
    && rm -rf /var/lib/apt/lists/*

RUN git clone --depth 1 https://github.com/ImageMagick/ImageMagick /src/ImageMagick \
 && git -C /src/ImageMagick fetch --depth 1 origin ${VULN_COMMIT} \
 && git -C /src/ImageMagick checkout ${VULN_COMMIT}

COPY harness/msl_fuzzer.cc /src/harness/msl_fuzzer.cc
COPY harness/utils.cc      /src/harness/utils.cc
COPY harness/build.sh      /src/harness/build.sh
RUN chmod +x /src/harness/build.sh

RUN /src/harness/build.sh build-libs
RUN mkdir -p /out \
 && /src/harness/build.sh harness debug \
 && /src/harness/build.sh harness debug-asan \
 && /src/harness/build.sh harness release-asan \
 && /src/harness/build.sh harness coverage

RUN ls -la /out/*/harness
